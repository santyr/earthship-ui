import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import org.osgi.framework.BundleActivator;
import org.osgi.framework.BundleContext;

/** Read-only HS103 peer, confined to an explicitly guarded disconnected JVM. */
public class HexTplinkLoopbackProbe implements BundleActivator {
    private final List<ServerSocket> servers = new ArrayList<>();
    private volatile boolean running;
    private static final String QUERY = "{\"system\":{\"get_sysinfo\":{}}}";

    private static byte[] crypt(byte[] bytes, boolean encrypt) {
        byte[] result = new byte[bytes.length];
        int key = 171;
        for (int i = 0; i < bytes.length; i++) {
            int wire = bytes[i] & 255;
            result[i] = (byte) (wire ^ key);
            key = encrypt ? result[i] & 255 : wire;
        }
        return result;
    }

    private static String read(DataInputStream input) throws IOException {
        int length = input.readInt();
        if (length < 1 || length > 8192) throw new IOException("invalid frame size");
        byte[] bytes = input.readNBytes(length);
        if (bytes.length != length) throw new IOException("truncated frame");
        return new String(crypt(bytes, false), StandardCharsets.UTF_8);
    }

    private static void write(DataOutputStream output, String text) throws IOException {
        byte[] bytes = crypt(text.getBytes(StandardCharsets.UTF_8), true);
        output.writeInt(bytes.length);
        output.write(bytes);
        output.flush();
    }

    @Override public void start(BundleContext context) throws Exception {
        if (!"1".equals(System.getenv("HEX_TPLINK_ISOLATED")))
            throw new IllegalStateException("disconnected fixture guard missing");
        running = true;
        try {
            for (int index = 1; index <= 2; index++) {
                final int device = index;
                final ServerSocket server = new ServerSocket(9999, 8,
                    InetAddress.getByName("127.0.0." + device));
                servers.add(server);
                Thread thread = new Thread(() -> {
                    long requests = 0, faults = 0, rejected = 0;
                    while (running) {
                        try (Socket socket = server.accept()) {
                            socket.setSoTimeout(3000);
                            String request = read(new DataInputStream(socket.getInputStream()));
                            requests++;
                            Path modePath = Path.of("/tmp/hex-tplink-mode-" + device);
                            String mode = Files.readString(modePath).trim();
                            if (!QUERY.equals(request)) {
                                rejected++;
                            } else if ("fault".equals(mode)) {
                                faults++;
                                // Close the real TCP transport without a response.
                            } else if ("healthy".equals(mode)) {
                                String sysinfo = "{\"system\":{\"get_sysinfo\":{" +
                                    "\"err_code\":0,\"model\":\"HS103(US)\",\"type\":\"IOT.SMARTPLUGSWITCH\"," +
                                    "\"sw_ver\":\"1.0\",\"hw_ver\":\"1.0\",\"alias\":\"Disconnected fixture\"," +
                                    "\"deviceId\":\"isolated-" + device + "\",\"mac\":\"00:00:00:00:00:0" + device + "\"," +
                                    "\"relay_state\":0,\"led_off\":0,\"feature\":\"TIM\",\"rssi\":-40,\"on_time\":0}}}";
                                write(new DataOutputStream(socket.getOutputStream()), sysinfo);
                            } else {
                                throw new IOException("unknown fixture mode");
                            }
                            Files.writeString(Path.of("/tmp/hex-tplink-wire-" + device),
                                "{\"requests\":" + requests + ",\"faults\":" + faults + ",\"rejected\":" + rejected + "}");
                        } catch (Exception error) {
                            if (running) System.out.println("tplink-fixture-error=" + error.getClass().getSimpleName());
                        }
                    }
                }, "isolated-tplink-peer-" + device);
                thread.setDaemon(true);
                thread.start();
            }
        } catch (Exception error) {
            stop(context);
            throw error;
        }
    }

    @Override public void stop(BundleContext context) throws Exception {
        running = false;
        for (ServerSocket server : servers) server.close();
        servers.clear();
    }

    /** Compare the fixture framing with the actual cached binding; no sockets. */
    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !"--self-test".equals(args[0]))
            throw new IllegalArgumentException("only offline self-test supported");
        Class<?> original = Class.forName("org.openhab.binding.tplinksmarthome.internal.CryptUtil");
        for (String value : List.of(QUERY, "{\"system\":{\"get_sysinfo\":{\"relay_state\":0}}}")) {
            java.io.ByteArrayOutputStream stream = new java.io.ByteArrayOutputStream();
            write(new DataOutputStream(stream), value);
            byte[] expected = (byte[]) original.getMethod("encryptWithLength", String.class).invoke(null, value);
            if (!Arrays.equals(expected, stream.toByteArray())) throw new IllegalStateException("wire encoding differs");
            String result = read(new DataInputStream(new java.io.ByteArrayInputStream(expected)));
            if (!value.equals(result)) throw new IllegalStateException("wire decoding differs");
        }
        for (int size : List.of(0, -1, 8193)) {
            java.io.ByteArrayOutputStream stream = new java.io.ByteArrayOutputStream();
            new DataOutputStream(stream).writeInt(size);
            try {
                read(new DataInputStream(new java.io.ByteArrayInputStream(stream.toByteArray())));
                throw new IllegalStateException("unsafe frame accepted");
            } catch (IOException expected) { }
        }
        byte[] shortFrame = {0, 0, 0, 4, 1};
        try {
            read(new DataInputStream(new java.io.ByteArrayInputStream(shortFrame)));
            throw new IllegalStateException("truncated frame accepted");
        } catch (IOException expected) { }
        System.out.println("actual_binding_wire_roundtrip_and_bounds=verified");
    }
}
