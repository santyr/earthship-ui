import {
  mkdtemp, readFile, readdir, rm, stat, writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  PHOTOSENSOR_ITEMS,
  PHOTOSENSOR_LINKS,
  JDBC_HISTORY_PATHS,
  RECEIPT_FILENAME,
  SNAPSHOT_FILENAME,
  THING_UID,
  applyTransaction,
  assertReceiptIntegrity,
  authorizePhotosensorRequest,
  buildApplyPlan,
  buildReceipt,
  buildRollbackPlan,
  canonicalDigest,
  closeTransaction,
  createRestClient,
  main,
  planTransaction,
  rehearseTransaction,
  rollbackTransaction,
  settleTransaction,
  snapshotTransaction,
  verifyTransaction,
} from "../scripts/thermal-photosensor-config.mjs";

const itemPath = (name) => `/rest/items/${encodeURIComponent(name)}`;
const linkPath = ({ itemName, channelUID }) => (
  `/rest/links/${encodeURIComponent(itemName)}/${encodeURIComponent(channelUID)}`
);

const temporaryDirectories = [];

async function receiptDirectory() {
  const directory = await mkdtemp(join(tmpdir(), "thermal-photosensor-test-"));
  temporaryDirectories.push(directory);
  return directory;
}

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((directory) => (
    rm(directory, { recursive: true, force: true })
  )));
});

function thingFixture() {
  return {
    UID: THING_UID,
    statusInfo: { status: "ONLINE", statusDetail: "NONE" },
    configuration: { networkkey: "must-never-enter-receipt" },
    channels: PHOTOSENSOR_LINKS.map((link, index) => ({
      uid: link.channelUID,
      id: link.channelUID.split(":").at(-1),
      kind: "STATE",
      itemType: PHOTOSENSOR_ITEMS[index].type,
      configuration: { private: "must-never-enter-receipt" },
    })),
  };
}

function jdbcFixture() {
  return {
    serviceId: "jdbc",
    editable: true,
    password: "must-never-enter-receipt",
    configs: [{
      items: ["*"],
      strategies: ["everyChange", "restoreOnStartup"],
      filters: [],
    }],
  };
}

function mutableTransport({
  items = {}, links = {}, failAfterWrite = null,
  thing = thingFixture(), jdbc = jdbcFixture(),
} = {}) {
  const currentItems = structuredClone(items);
  const currentLinks = structuredClone(links);
  const calls = [];
  let writes = 0;
  const request = async (method, path, options = {}) => {
    const record = { method, path };
    if (Object.hasOwn(options, "body")) record.body = structuredClone(options.body);
    calls.push(record);
    if (method === "GET" && path.includes("/rest/things/")) return structuredClone(thing);
    if (method === "GET" && path === "/rest/persistence/jdbc") return structuredClone(jdbc);
    const item = PHOTOSENSOR_ITEMS.find(({ name }) => itemPath(name) === path);
    const link = PHOTOSENSOR_LINKS.find((entry) => linkPath(entry) === path);
    const store = item ? currentItems : currentLinks;
    const key = item?.name ?? link?.itemName;
    if (!key) throw new Error(`unexpected fake path ${path}`);
    if (method === "GET") return structuredClone(store[key] ?? null);
    if (method === "PUT") store[key] = structuredClone(options.body);
    else if (method === "DELETE") delete store[key];
    else throw new Error(`unexpected fake method ${method}`);
    writes += 1;
    if (failAfterWrite === writes) throw new Error("connection closed after write");
    return null;
  };
  return {
    calls,
    request,
    resources: () => ({
      items: structuredClone(currentItems),
      links: structuredClone(currentLinks),
    }),
    clearFailure: () => { failAfterWrite = null; },
    setFailureAfterAdditional: (count) => { failAfterWrite = writes + count; },
  };
}

describe("thermal photosensor manifest", () => {
  it("owns exactly the hallway living-office observation Items and channels", () => {
    expect(THING_UID).toBe("zigbee:device:a7351eb531:001788011024c307");
    expect(PHOTOSENSOR_ITEMS.map(({ name, type }) => ({ name, type }))).toEqual([
      { name: "LivingOffice_Shade_Illuminance", type: "Number" },
      { name: "LivingOffice_Shade_Occupancy", type: "Switch" },
      { name: "LivingOffice_Shade_Temperature", type: "Number:Temperature" },
    ]);
    expect(PHOTOSENSOR_LINKS.map(({ itemName, channelUID }) => ({
      itemName, channelUID,
    }))).toEqual([
      {
        itemName: "LivingOffice_Shade_Illuminance",
        channelUID: `${THING_UID}:001788011024C307_2_illuminance`,
      },
      {
        itemName: "LivingOffice_Shade_Occupancy",
        channelUID: `${THING_UID}:001788011024C307_2_occupancy`,
      },
      {
        itemName: "LivingOffice_Shade_Temperature",
        channelUID: `${THING_UID}:001788011024C307_2_temperature`,
      },
    ]);
    expect(JSON.stringify({ PHOTOSENSOR_ITEMS, PHOTOSENSOR_LINKS }))
      .not.toMatch(/command|actuator|Thermal_Advisory|state/i);
  });

  it("builds Items first and links second, with reverse rollback order", () => {
    const original = {
      items: Object.fromEntries(PHOTOSENSOR_ITEMS.map(({ name }) => [name, null])),
      links: Object.fromEntries(PHOTOSENSOR_LINKS.map(({ itemName }) => [itemName, null])),
    };

    const apply = buildApplyPlan(original);
    expect(apply).toHaveLength(6);
    expect(apply.slice(0, 3).map(({ method, path }) => [method, path])).toEqual(
      PHOTOSENSOR_ITEMS.map(({ name }) => ["PUT", itemPath(name)]),
    );
    expect(apply.slice(3).map(({ method, path }) => [method, path])).toEqual(
      PHOTOSENSOR_LINKS.map((link) => ["PUT", linkPath(link)]),
    );
    expect(buildRollbackPlan(original).map(({ method, path }) => ({ method, path })))
      .toEqual([
      ...PHOTOSENSOR_LINKS.toReversed().map((link) => ({
        method: "DELETE", path: linkPath(link),
      })),
      ...PHOTOSENSOR_ITEMS.toReversed().map(({ name }) => ({
        method: "DELETE", path: itemPath(name),
      })),
      ]);
  });
});

describe("closed photosensor request authority", () => {
  it("allows only exact observation GETs and receipt-bound configuration writes", () => {
    for (const item of PHOTOSENSOR_ITEMS) {
      expect(() => authorizePhotosensorRequest("GET", itemPath(item.name)))
        .not.toThrow();
    }
    for (const link of PHOTOSENSOR_LINKS) {
      expect(() => authorizePhotosensorRequest("GET", linkPath(link)))
        .not.toThrow();
    }
    for (const path of JDBC_HISTORY_PATHS) {
      expect(() => authorizePhotosensorRequest("GET", path)).not.toThrow();
      expect(() => authorizePhotosensorRequest("PUT", path, { body: {} }))
        .toThrow(/denied/i);
    }

    for (const [method, path] of [
      ["PUT", `/rest/things/${encodeURIComponent(THING_UID)}`],
      ["DELETE", `/rest/things/${encodeURIComponent(THING_UID)}`],
      ["PUT", "/rest/persistence/jdbc"],
      ["PUT", "/rest/items/LivingOffice_Shade_Illuminance/state"],
      ["PUT", "/rest/rules/invented"],
      ["PUT", "/rest/items/Thermal_Advisory"],
      ["GET", "/rest/items/Unrelated"],
      ["GET", `${itemPath(PHOTOSENSOR_ITEMS[0].name)}?x=1`],
    ]) {
      expect(() => authorizePhotosensorRequest(method, path)).toThrow(/denied/i);
    }
  });

  it("requires the exact transaction-owned Item or link body", () => {
    const original = {
      items: Object.fromEntries(PHOTOSENSOR_ITEMS.map(({ name }) => [name, null])),
      links: Object.fromEntries(PHOTOSENSOR_LINKS.map(({ itemName }) => [itemName, null])),
      thing: {
        uid: THING_UID, status: "ONLINE", channels: PHOTOSENSOR_LINKS.map((link, index) => ({
          uid: link.channelUID, kind: "STATE", itemType: PHOTOSENSOR_ITEMS[index].type,
        })),
      },
      jdbc: {
        serviceId: "jdbc", editable: true,
        wildcardStrategies: ["everyChange", "restoreOnStartup"],
      },
    };
    const transaction = { operation: "apply", ...buildReceipt(original) };
    const operation = buildApplyPlan(original)[0];
    expect(() => authorizePhotosensorRequest(operation.method, operation.path, {
      body: operation.body, transaction,
    })).not.toThrow();
    expect(() => authorizePhotosensorRequest(operation.method, operation.path, {
      body: { ...operation.body, type: "Switch" }, transaction,
    })).toThrow(/denied/i);
    expect(() => authorizePhotosensorRequest("PUT", operation.path, {
      body: { ...operation.body, state: "12" }, transaction,
    })).toThrow(/denied/i);
  });

  it("requires empty desired link config but restores captured link config exactly", () => {
    const existingLink = {
      ...PHOTOSENSOR_LINKS[0],
      configuration: { profile: "system:default" },
    };
    const original = {
      items: Object.fromEntries(PHOTOSENSOR_ITEMS.map((entry) => [entry.name, null])),
      links: Object.fromEntries(PHOTOSENSOR_LINKS.map((entry) => [
        entry.itemName, entry.itemName === existingLink.itemName ? existingLink : null,
      ])),
      thing: {
        uid: THING_UID, status: "ONLINE",
        channels: PHOTOSENSOR_LINKS.map((entry, index) => ({
          uid: entry.channelUID, kind: "STATE", itemType: PHOTOSENSOR_ITEMS[index].type,
        })),
      },
      jdbc: {
        serviceId: "jdbc", editable: true,
        wildcardStrategies: ["everyChange", "restoreOnStartup"],
      },
    };
    const built = buildReceipt(original, { createdAt: "2026-08-20T16:00:00.000Z" });
    const apply = buildApplyPlan(built.snapshot).find(({ path }) => (
      path === linkPath(PHOTOSENSOR_LINKS[0])
    ));
    const rollback = buildRollbackPlan(built.snapshot).find(({ path }) => (
      path === linkPath(PHOTOSENSOR_LINKS[0])
    ));
    expect(apply.body.configuration).toEqual({});
    expect(rollback.body.configuration).toEqual({ profile: "system:default" });
    expect(() => authorizePhotosensorRequest(apply.method, apply.path, {
      body: { ...apply.body, configuration: { profile: "invented" } },
      transaction: { operation: "apply", ...built },
    })).toThrow(/denied/i);
    expect(() => authorizePhotosensorRequest(rollback.method, rollback.path, {
      body: rollback.body,
      transaction: { operation: "rollback", ...built },
    })).not.toThrow();
  });
});

describe("receipt-bound multi-resource transaction", () => {
  it.each([
    ["offline Thing", { thing: { ...thingFixture(), statusInfo: { status: "OFFLINE" } } }],
    ["missing channel", { thing: { ...thingFixture(), channels: thingFixture().channels.slice(0, 2) } }],
    ["missing JDBC strategy", {
      jdbc: {
        ...jdbcFixture(),
        configs: [{ items: ["*"], strategies: ["everyChange"], filters: [] }],
      },
    }],
  ])("fails %s preflight before writing receipt files", async (_label, options) => {
    const directory = await receiptDirectory();
    const transport = mutableTransport(options);

    await expect(snapshotTransaction({
      request: transport.request, receiptDir: directory,
    })).rejects.toThrow(/Thing|channel|JDBC|persistence/i);
    await expect(readFile(join(directory, RECEIPT_FILENAME))).rejects.toMatchObject({
      code: "ENOENT",
    });
  });

  it("snapshots only sanitized evidence in private durable files", async () => {
    const directory = await receiptDirectory();
    const transport = mutableTransport();

    const { receipt, snapshot } = await snapshotTransaction({
      request: transport.request,
      receiptDir: directory,
      now: () => new Date("2026-08-20T16:00:00.000Z"),
    });

    expect(() => assertReceiptIntegrity(receipt, snapshot)).not.toThrow();
    expect(snapshot.thing.status).toBe("ONLINE");
    expect(snapshot.jdbc.wildcardStrategies).toEqual([
      "everyChange", "restoreOnStartup",
    ]);
    expect(JSON.stringify(snapshot)).not.toMatch(/networkkey|password|private|token/i);
    expect((await stat(directory)).mode & 0o777).toBe(0o700);
    expect((await stat(join(directory, RECEIPT_FILENAME))).mode & 0o777).toBe(0o600);
    expect((await stat(join(directory, SNAPSHOT_FILENAME))).mode & 0o777).toBe(0o600);
  });

  it("selects the three owned channels from a Thing with unrelated channels", async () => {
    const directory = await receiptDirectory();
    const thing = thingFixture();
    thing.channels.push({
      uid: `${THING_UID}:battery_level`,
      id: "battery_level",
      kind: "STATE",
      itemType: "Number:Dimensionless",
      configuration: { private: "must-never-enter-receipt" },
    });

    const { snapshot } = await snapshotTransaction({
      request: mutableTransport({ thing }).request,
      receiptDir: directory,
    });

    expect(snapshot.thing.channels).toHaveLength(3);
    expect(snapshot.thing.channels.map(({ uid }) => uid)).toEqual(
      PHOTOSENSOR_LINKS.map(({ channelUID }) => channelUID),
    );
    expect(JSON.stringify(snapshot)).not.toContain("battery_level");
  });

  it("applies exactly six writes, verifies, closes, and rolls back exactly", async () => {
    const directory = await receiptDirectory();
    const transport = mutableTransport();
    await snapshotTransaction({ request: transport.request, receiptDir: directory });
    transport.calls.length = 0;

    const applied = await applyTransaction({
      request: transport.request, receiptDir: directory,
    });
    expect(applied.phase).toBe("desired");
    expect(applied.writeCount).toBe(6);
    expect(transport.calls.filter(({ method }) => ["PUT", "DELETE"].includes(method)))
      .toEqual(buildApplyPlan(applied.snapshot ?? {
        items: Object.fromEntries(PHOTOSENSOR_ITEMS.map(({ name }) => [name, null])),
        links: Object.fromEntries(PHOTOSENSOR_LINKS.map(({ itemName }) => [itemName, null])),
      }).map(({ method, path, body }) => ({ method, path, body })));
    await expect(verifyTransaction({ request: transport.request, receiptDir: directory }))
      .resolves.toMatchObject({ ok: true, expected: "desired" });
    await closeTransaction({ request: transport.request, receiptDir: directory });

    const rolledBack = await rollbackTransaction({
      request: transport.request, receiptDir: directory,
    });
    expect(rolledBack.phase).toBe("rolled-back");
    expect(Object.keys(transport.resources().items)).toEqual([]);
    expect(Object.keys(transport.resources().links)).toEqual([]);
    await expect(verifyTransaction({ request: transport.request, receiptDir: directory }))
      .resolves.toMatchObject({ ok: true, expected: "original" });
  });

  it("refuses captured pre-state drift before its first OpenHAB write", async () => {
    const directory = await receiptDirectory();
    await snapshotTransaction({
      request: mutableTransport().request, receiptDir: directory,
    });
    const drifted = mutableTransport({
      items: {
        [PHOTOSENSOR_ITEMS[0].name]: {
          ...PHOTOSENSOR_ITEMS[0], label: "Changed elsewhere",
        },
      },
    });

    await expect(applyTransaction({
      request: drifted.request, receiptDir: directory,
    })).rejects.toThrow(/drift/i);
    expect(drifted.calls.filter(({ method }) => ["PUT", "DELETE"].includes(method)))
      .toEqual([]);
  });

  it("never retries an ambiguous write and resumes only after exact settlement", async () => {
    const directory = await receiptDirectory();
    const transport = mutableTransport({ failAfterWrite: 4 });
    await snapshotTransaction({ request: transport.request, receiptDir: directory });
    transport.calls.length = 0;

    await expect(applyTransaction({
      request: transport.request, receiptDir: directory,
    })).rejects.toThrow(/connection closed/i);
    expect(transport.calls.filter(({ method }) => method === "PUT")).toHaveLength(4);
    await expect(applyTransaction({
      request: transport.request, receiptDir: directory,
    })).rejects.toThrow(/settle/i);

    const settled = await settleTransaction({
      request: transport.request, receiptDir: directory,
    });
    expect(settled).toMatchObject({ phase: "applying", nextOperation: 4 });
    transport.clearFailure();
    const resumed = await applyTransaction({
      request: transport.request, receiptDir: directory,
    });
    expect(resumed).toMatchObject({ phase: "desired", writeCount: 6 });
    const writes = transport.calls.filter(({ method }) => method === "PUT");
    expect(writes.filter(({ path }) => path === linkPath(PHOTOSENSOR_LINKS[0])))
      .toHaveLength(1);
  });

  it("rehearses apply, rollback, verify, and close without changing real bytes", async () => {
    const directory = await receiptDirectory();
    const transport = mutableTransport();
    await snapshotTransaction({ request: transport.request, receiptDir: directory });
    const beforeReceipt = await readFile(join(directory, RECEIPT_FILENAME));
    const beforeSnapshot = await readFile(join(directory, SNAPSHOT_FILENAME));

    const result = await rehearseTransaction({ receiptDir: directory });

    expect(result.writeCounts).toEqual({ put: 6, delete: 6, total: 12 });
    expect(result.terminal).toMatchObject({ state: "closed", phase: "rolled-back" });
    expect(await readFile(join(directory, RECEIPT_FILENAME))).toEqual(beforeReceipt);
    expect(await readFile(join(directory, SNAPSHOT_FILENAME))).toEqual(beforeSnapshot);
  });

  it.each([1, 2, 3, 4, 5, 6])(
    "recovers an ambiguous apply at write boundary %i without retry",
    async (boundary) => {
      const directory = await receiptDirectory();
      const transport = mutableTransport({ failAfterWrite: boundary });
      await snapshotTransaction({ request: transport.request, receiptDir: directory });
      await expect(applyTransaction({
        request: transport.request, receiptDir: directory,
      })).rejects.toThrow(/connection closed/i);
      const path = buildApplyPlan({
        items: Object.fromEntries(PHOTOSENSOR_ITEMS.map(({ name }) => [name, null])),
        links: Object.fromEntries(PHOTOSENSOR_LINKS.map(({ itemName }) => [itemName, null])),
      })[boundary - 1].path;
      expect(transport.calls.filter(({ method, path: called }) => (
        method === "PUT" && called === path
      ))).toHaveLength(1);

      const settled = await settleTransaction({
        request: transport.request, receiptDir: directory,
      });
      expect(settled.nextOperation).toBe(boundary);
      transport.clearFailure();
      if (settled.phase !== "desired") {
        await applyTransaction({ request: transport.request, receiptDir: directory });
      }
      await expect(verifyTransaction({
        request: transport.request, receiptDir: directory,
      })).resolves.toMatchObject({ ok: true, expected: "desired" });
      expect(transport.calls.filter(({ method, path: called }) => (
        method === "PUT" && called === path
      ))).toHaveLength(1);
    },
  );

  it.each([1, 2, 3, 4, 5, 6])(
    "recovers an ambiguous rollback at write boundary %i without retry",
    async (boundary) => {
      const directory = await receiptDirectory();
      const transport = mutableTransport();
      await snapshotTransaction({ request: transport.request, receiptDir: directory });
      await applyTransaction({ request: transport.request, receiptDir: directory });
      transport.setFailureAfterAdditional(boundary);
      await expect(rollbackTransaction({
        request: transport.request, receiptDir: directory,
      })).rejects.toThrow(/connection closed/i);
      const plan = buildRollbackPlan({
        items: Object.fromEntries(PHOTOSENSOR_ITEMS.map(({ name }) => [name, null])),
        links: Object.fromEntries(PHOTOSENSOR_LINKS.map(({ itemName }) => [itemName, null])),
      });
      const path = plan[boundary - 1].path;
      expect(transport.calls.filter(({ method, path: called }) => (
        method === "DELETE" && called === path
      ))).toHaveLength(1);

      const settled = await settleTransaction({
        request: transport.request, receiptDir: directory,
      });
      transport.clearFailure();
      if (settled.phase !== "rolled-back") {
        await rollbackTransaction({ request: transport.request, receiptDir: directory });
      }
      await expect(verifyTransaction({
        request: transport.request, receiptDir: directory,
      })).resolves.toMatchObject({ ok: true, expected: "original" });
      expect(transport.calls.filter(({ method, path: called }) => (
        method === "DELETE" && called === path
      ))).toHaveLength(1);
    },
  );

  it("rejects a tampered receipt before contacting OpenHAB", async () => {
    const directory = await receiptDirectory();
    const initial = mutableTransport();
    await snapshotTransaction({ request: initial.request, receiptDir: directory });
    const receiptPath = join(directory, RECEIPT_FILENAME);
    const receipt = JSON.parse(await readFile(receiptPath, "utf8"));
    receipt.writeCount = 99;
    await writeFile(receiptPath, `${JSON.stringify(receipt)}\n`, "utf8");
    const transport = mutableTransport();

    await expect(applyTransaction({
      request: transport.request, receiptDir: directory,
    })).rejects.toThrow(/checksum/i);
    expect(transport.calls).toEqual([]);
  });

  it("rejects unknown receipt fields even with a recomputed checksum", () => {
    const original = {
      items: Object.fromEntries(PHOTOSENSOR_ITEMS.map(({ name }) => [name, null])),
      links: Object.fromEntries(PHOTOSENSOR_LINKS.map(({ itemName }) => [itemName, null])),
      thing: {
        uid: THING_UID,
        status: "ONLINE",
        channels: PHOTOSENSOR_LINKS.map((link, index) => ({
          uid: link.channelUID,
          kind: "STATE",
          itemType: PHOTOSENSOR_ITEMS[index].type,
        })),
      },
      jdbc: {
        serviceId: "jdbc", editable: true,
        wildcardStrategies: ["everyChange", "restoreOnStartup"],
      },
    };
    const { receipt, snapshot } = buildReceipt(original, {
      createdAt: "2026-08-20T16:00:00.000Z",
    });
    receipt.invented = true;
    receipt.checksum = canonicalDigest(receipt);

    expect(() => assertReceiptIntegrity(receipt, snapshot)).toThrow(/fields/i);
  });

  it("holds an exclusive durable lock and removes locks and unique temps", async () => {
    const directory = await receiptDirectory();
    const base = mutableTransport();
    let releaseFirst;
    let enteredFirst;
    const entered = new Promise((resolve) => { enteredFirst = resolve; });
    const blocked = new Promise((resolve) => { releaseFirst = resolve; });
    let firstGet = true;
    const request = async (...args) => {
      if (firstGet) {
        firstGet = false;
        enteredFirst();
        await blocked;
      }
      return base.request(...args);
    };
    const first = snapshotTransaction({ request, receiptDir: directory });
    await entered;

    await expect(snapshotTransaction({
      request: base.request, receiptDir: directory,
    })).rejects.toThrow(/busy|lock/i);
    releaseFirst();
    await first;
    const names = await readdir(directory);
    expect(names).not.toContain("transaction.lock");
    expect(names.filter((name) => name.includes(".tmp-"))).toEqual([]);
  });

  it("makes close idempotent after exact terminal readback", async () => {
    const directory = await receiptDirectory();
    const transport = mutableTransport();
    await snapshotTransaction({ request: transport.request, receiptDir: directory });
    await applyTransaction({ request: transport.request, receiptDir: directory });
    const first = await closeTransaction({
      request: transport.request, receiptDir: directory,
    });
    const bytes = await readFile(join(directory, RECEIPT_FILENAME));
    const second = await closeTransaction({
      request: transport.request, receiptDir: directory,
    });
    expect(second).toEqual(first);
    expect(await readFile(join(directory, RECEIPT_FILENAME))).toEqual(bytes);
  });

  it("plans without loading authorization and exposes only receipt-bound packets", async () => {
    const directory = await receiptDirectory();
    const transport = mutableTransport();
    await snapshotTransaction({ request: transport.request, receiptDir: directory });

    const direct = await planTransaction({ receiptDir: directory });
    const cli = await main(["plan", "--receipt-dir", directory]);

    expect(cli.apply).toEqual(direct.apply);
    expect(cli.rollback).toEqual(direct.rollback);
    expect(JSON.stringify(cli)).not.toMatch(/authorization|token|networkkey|password/i);
  });
});

describe("confined photosensor REST client", () => {
  it("sends an exact allowed packet and disables redirects", async () => {
    const calls = [];
    const request = createRestClient({
      baseUrl: "https://openhab.test/",
      authorization: "Basic fixture",
      fetchImpl: async (...args) => {
        calls.push(args);
        return {
          ok: true, redirected: false, status: 200,
          text: async () => JSON.stringify(thingFixture()),
        };
      },
    });

    await request("GET", `/rest/things/${encodeURIComponent(THING_UID)}`);

    expect(calls).toHaveLength(1);
    expect(calls[0][0]).toBe(
      `https://openhab.test/rest/things/${encodeURIComponent(THING_UID)}`,
    );
    expect(calls[0][1]).toMatchObject({ method: "GET", redirect: "error" });
  });

  it("confines the exact JDBC history query without allowing alternate queries", async () => {
    const calls = [];
    const request = createRestClient({
      baseUrl: "https://openhab.test",
      authorization: "Basic fixture",
      fetchImpl: async (...args) => {
        calls.push(args);
        return {
          ok: true, redirected: false, status: 200,
          text: async () => "[]",
        };
      },
    });

    await request("GET", JDBC_HISTORY_PATHS[0]);
    await expect(request("GET", `${JDBC_HISTORY_PATHS[0]}&page=1`))
      .rejects.toThrow(/denied/i);
    expect(calls).toHaveLength(1);
    expect(calls[0][0]).toBe(`https://openhab.test${JDBC_HISTORY_PATHS[0]}`);
  });

  it.each([
    "ftp://openhab.test",
    "https://user:pass@openhab.test",
    "https://openhab.test/rest",
    "https://openhab.test/?token=bad",
  ])("rejects unsafe base URL %s before fetch", (baseUrl) => {
    const calls = [];
    expect(() => createRestClient({
      baseUrl, authorization: "Basic fixture", fetchImpl: (...args) => calls.push(args),
    })).toThrow(/denied|invalid/i);
    expect(calls).toEqual([]);
  });
});
