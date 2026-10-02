import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.osgi.framework.BundleActivator;
import org.osgi.framework.BundleContext;

/** HTTP source fixture; can only start inside the disconnected qualification. */
public final class HexRadiationHttpProbe implements BundleActivator {
    private ServerSocket server;
    private volatile boolean running;

    public void start(BundleContext context) throws Exception {
        if (!"1".equals(System.getenv("HEX_JDBC_ISOLATED"))) {
            throw new IllegalStateException("isolated fixture guard missing");
        }
        server = new ServerSocket(5000, 8, InetAddress.getLoopbackAddress());
        running = true;
        Thread worker = new Thread(() -> {
            while (running) {
                try (Socket client = server.accept()) {
                    client.setSoTimeout(3000);
                    BufferedReader input = new BufferedReader(new InputStreamReader(
                            client.getInputStream(), StandardCharsets.UTF_8));
                    String request = input.readLine();
                    for (int i = 0; i < 64; i++) {
                        String header = input.readLine();
                        if (header == null || header.isEmpty()) break;
                    }
                    String value = Files.readString(Path.of("/tmp/radiation-http-response"));
                    if (value.length() > 8192) throw new IllegalArgumentException("fixture bound");
                    int split = value.indexOf('\n');
                    int status = Integer.parseInt(value.substring(0, split));
                    byte[] body = value.substring(split + 1).getBytes(StandardCharsets.UTF_8);
                    if (!"GET /radiation_evidence HTTP/1.1".equals(request)) status = 404;
                    String headers = "HTTP/1.1 " + status + " Fixture\r\n"
                            + "Content-Type: application/json\r\nCache-Control: no-store\r\n"
                            + "Connection: close\r\nContent-Length: " + body.length + "\r\n\r\n";
                    client.getOutputStream().write(headers.getBytes(StandardCharsets.UTF_8));
                    client.getOutputStream().write(body);
                    Files.writeString(Path.of("/tmp/radiation-http-last-status"),
                            Integer.toString(status));
                } catch (Exception error) {
                    if (running) System.err.println("isolated radiation HTTP fixture error: "
                            + error.getClass().getSimpleName());
                }
            }
        }, "isolated-radiation-http");
        worker.setDaemon(true);
        worker.start();
    }

    public void stop(BundleContext context) throws Exception {
        running = false;
        if (server != null) server.close();
    }
}
