import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.time.Instant;
import java.time.InstantSource;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.GregorianCalendar;
import org.openhab.binding.astro.internal.calc.SunCalc;

/** One bounded batch against the installed Astro library, without an OSGi runtime. */
class NativeSolarGeometry {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("one original request file required");
        Path file = Path.of(args[0]);
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS) || Files.size(file) > 16384)
            throw new IllegalArgumentException("bounded regular request file required");
        var lines = Files.readAllLines(file, StandardCharsets.US_ASCII);
        if (lines.size() < 3 || lines.size() > 258)
            throw new IllegalArgumentException("one to 256 exact timestamps required");
        Instant known = ZonedDateTime.parse(lines.get(0)).toInstant();
        String[] site = lines.get(1).split("\t", -1);
        if (site.length != 2) throw new IllegalArgumentException("explicit coordinates required");
        double latitude = Double.parseDouble(site[0]), longitude = Double.parseDouble(site[1]);
        if (!Double.isFinite(latitude) || !Double.isFinite(longitude) ||
                latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180)
            throw new IllegalArgumentException("physical coordinates required");
        var points = new ArrayList<ZonedDateTime>();
        Instant previous = null;
        for (String text : lines.subList(2, lines.size())) {
            var at = ZonedDateTime.parse(text);
            Instant instant = at.toInstant();
            if (instant.getNano() % 1000000 != 0 || previous != null && !previous.isBefore(instant))
                throw new IllegalArgumentException("unique ordered millisecond timestamps required");
            points.add(at);previous = instant;
        }
        SunCalc calculator = new SunCalc(InstantSource.fixed(known));
        for (var at : points) {
            var position = calculator.getPosition(GregorianCalendar.from(at), latitude, longitude);
            double elevation = position.getElevationAsDouble(), azimuth = position.getAzimuthAsDouble();
            if (!Double.isFinite(elevation) || !Double.isFinite(azimuth) ||
                    elevation < -90 || elevation > 90 || azimuth < 0 || azimuth > 360)
                throw new IllegalStateException("native position unavailable");
            System.out.println(at.toInstant() + "\t" + elevation + "\t" + azimuth);
        }
    }
}
