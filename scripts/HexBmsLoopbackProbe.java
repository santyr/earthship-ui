import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInput;
import java.io.DataInputStream;
import java.io.DataOutput;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.osgi.framework.BundleActivator;
import org.osgi.framework.BundleContext;

/** No write implementation; only the original unit-190 holding-register read. */
public final class HexBmsLoopbackProbe implements BundleActivator {
    private ServerSocket server;
    private volatile boolean running;
    private long requests, faults, rejected;

    private static int read(DataInputStream input) throws IOException {
        int transaction = input.readUnsignedShort();
        int protocol = input.readUnsignedShort();
        int length = input.readUnsignedShort();
        // Only MBAP + unit + function 3 + address/quantity, never arbitrary PDUs.
        if (protocol != 0 || length != 6) throw new IOException("unsafe MBAP frame");
        byte[] pdu = input.readNBytes(length);
        if (pdu.length != length) throw new IOException("truncated MBAP frame");
        DataInputStream body = new DataInputStream(new ByteArrayInputStream(pdu));
        if (body.readUnsignedByte() != 190 || body.readUnsignedByte() != 3
                || body.readUnsignedShort() != 64 || body.readUnsignedShort() != 34)
            throw new IOException("request outside read-only register scope");
        return transaction;
    }

    private static byte[] response(int transaction) throws IOException {
        ByteArrayOutputStream stream = new ByteArrayOutputStream();
        DataOutputStream output = new DataOutputStream(stream);
        output.writeShort(transaction);
        output.writeShort(0);
        output.writeShort(71);
        output.writeByte(190);
        output.writeByte(3);
        output.writeByte(68);
        for (int address = 64; address < 98; address++) {
            // uint32 high word then low word, matching the exact native map.
            output.writeShort(address == 75 ? 29315 : address == 89 ? 320 : 0);
        }
        return stream.toByteArray();
    }

    private void marker() throws IOException {
        Files.writeString(Path.of("/tmp/hex-bms-wire"),
            "{\"requests\":" + requests + ",\"faults\":" + faults + ",\"rejected\":" + rejected + "}");
    }

    @Override public void start(BundleContext context) throws Exception {
        if (!"1".equals(System.getenv("HEX_BMS_ISOLATED")))
            throw new IllegalStateException("disconnected fixture guard missing");
        server = new ServerSocket(1503, 8, InetAddress.getByName("127.0.0.1"));
        running = true;
        Thread thread = new Thread(() -> {
            while (running) {
                try (Socket socket = server.accept()) {
                    socket.setSoTimeout(45000);
                    DataInputStream input = new DataInputStream(socket.getInputStream());
                    DataOutputStream output = new DataOutputStream(socket.getOutputStream());
                    while (running) {
                        int transaction;
                        try { transaction = read(input); }
                        catch (EOFException closed) { break; }
                        catch (IOException unsafe) { rejected++; marker(); break; }
                        requests++;
                        String mode = Files.readString(Path.of("/tmp/hex-bms-mode")).trim();
                        if ("fault".equals(mode)) {
                            faults++;
                            marker();
                            break; // Actual TCP EOF; no injected Item/Thing status.
                        }
                        if (!"healthy".equals(mode)) throw new IOException("unknown fixture mode");
                        output.write(response(transaction));
                        output.flush();
                        marker();
                    }
                } catch (Exception error) {
                    if (running) System.out.println("bms-fixture-error=" + error.getClass().getSimpleName());
                }
            }
        }, "isolated-bms-modbus-peer");
        thread.setDaemon(true);
        thread.start();
    }

    @Override public void stop(BundleContext context) throws Exception {
        running = false;
        if (server != null) server.close();
    }

    /** Offline self-test uses the embedded protocol implementation, no sockets. */
    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !"--self-test".equals(args[0]))
            throw new IllegalArgumentException("only offline self-test supported");
        Class<?> requestType = Class.forName("net.wimpi.modbus.msg.ReadMultipleRegistersRequest");
        Object request = requestType.getConstructor(int.class, int.class).newInstance(64, 34);
        requestType.getMethod("setUnitID", int.class).invoke(request, 190);
        requestType.getMethod("setTransactionID", int.class).invoke(request, 7);
        ByteArrayOutputStream encoded = new ByteArrayOutputStream();
        requestType.getMethod("writeTo", DataOutput.class).invoke(request, new DataOutputStream(encoded));
        byte[] original = encoded.toByteArray();
        if (read(new DataInputStream(new ByteArrayInputStream(original))) != 7)
            throw new IllegalStateException("request decoding differs");
        Class<?> responseType = Class.forName("net.wimpi.modbus.msg.ReadMultipleRegistersResponse");
        Object reply = responseType.getConstructor().newInstance();
        responseType.getMethod("readFrom", DataInput.class).invoke(reply,
            new DataInputStream(new ByteArrayInputStream(response(7))));
        if ((int) responseType.getMethod("getWordCount").invoke(reply) != 34
                || (int) responseType.getMethod("getTransactionID").invoke(reply) != 7
                || (int) responseType.getMethod("getUnitID").invoke(reply) != 190
                || (int) responseType.getMethod("getRegisterValue", int.class).invoke(reply, 11) != 29315
                || (int) responseType.getMethod("getRegisterValue", int.class).invoke(reply, 25) != 320)
            throw new IllegalStateException("response decoding differs");
        for (int index : List.of(2, 5, 6, 7, 9, 11)) {
            byte[] unsafe = original.clone();
            unsafe[index] ^= 1;
            try {
                read(new DataInputStream(new ByteArrayInputStream(unsafe)));
                throw new IllegalStateException("unsafe request accepted");
            } catch (IOException expected) { }
        }
        byte[] truncated = java.util.Arrays.copyOf(original, original.length - 1);
        try {
            read(new DataInputStream(new ByteArrayInputStream(truncated)));
            throw new IllegalStateException("truncated request accepted");
        } catch (IOException expected) { }
        System.out.println("actual_modbus_protocol_roundtrip_and_read_only_bounds=verified");
    }
}
