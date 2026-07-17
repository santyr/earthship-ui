export function createClient({ openhabUrl, apiToken }) {
  const h = { Authorization: `Bearer ${apiToken}` };
  const base = openhabUrl.replace(/\/$/, '');
  return {
    async getAllItems() {
      const r = await fetch(`${base}/rest/items?fields=name,state,type`, { headers: h });
      if (!r.ok) throw new Error(`getAllItems ${r.status}`);
      return r.json();
    },
    async getItem(name) {
      const r = await fetch(`${base}/rest/items/${name}`, { headers: h });
      if (!r.ok) throw new Error(`getItem ${name} ${r.status}`);
      return r.json();
    },
    async sendCommand(name, value) {
      const r = await fetch(`${base}/rest/items/${name}`, {
        method: 'POST', headers: { ...h, 'Content-Type': 'text/plain' }, body: String(value) });
      if (!r.ok) throw new Error(`sendCommand ${name} ${r.status}`);
    },
    async getHistory(name, { starttime, endtime }) {
      const q = new URLSearchParams({ starttime, endtime });
      const r = await fetch(`${base}/rest/persistence/items/${name}?${q}`, { headers: h });
      if (!r.ok) throw new Error(`getHistory ${name} ${r.status}`);
      const d = await r.json();
      return (d.data || []).map((p) => ({ time: p.time, state: parseFloat(String(p.state)) }));
    },
  };
}
