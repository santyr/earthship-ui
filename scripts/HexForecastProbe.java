import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;

import org.openhab.core.events.EventPublisher;
import org.openhab.core.items.events.ItemEventFactory;
import org.openhab.core.library.types.DecimalType;
import org.openhab.core.types.TimeSeries;
import org.osgi.framework.BundleActivator;
import org.osgi.framework.BundleContext;
import org.osgi.framework.ServiceReference;

/** Publishes one synthetic forecast only inside the disconnected JDBC fixture. */
public final class HexForecastProbe implements BundleActivator {
    @Override
    public void start(BundleContext context) throws Exception {
        if (!"1".equals(System.getenv("HEX_JDBC_ISOLATED"))) {
            throw new IllegalStateException("isolated fixture guard missing");
        }
        List<String> input = Files.readAllLines(Path.of("/tmp/hex-jdbc-forecast-probe"));
        if (input.size() != 2) {
            throw new IllegalArgumentException("expected target and value");
        }
        Instant target = Instant.parse(input.get(0));
        if (!target.isAfter(Instant.now().plusSeconds(3600))) {
            throw new IllegalArgumentException("target must be in the future");
        }
        int value = Integer.parseInt(input.get(1));
        if (value < 1 || value > 1000) {
            throw new IllegalArgumentException("bounded synthetic value required");
        }
        ServiceReference<EventPublisher> reference = context.getServiceReference(EventPublisher.class);
        if (reference == null) {
            throw new IllegalStateException("event publisher unavailable");
        }
        EventPublisher publisher = context.getService(reference);
        if (publisher == null) {
            throw new IllegalStateException("event publisher service unavailable");
        }
        try {
            TimeSeries series = new TimeSeries(TimeSeries.Policy.REPLACE);
            series.add(target, new DecimalType(value));
            series.add(target.plusSeconds(3600), new DecimalType(value + 1));
            publisher.post(ItemEventFactory.createTimeSeriesEvent(
                    "JDBC_Forecast_Probe", series, "hex-isolated-qualification"));
            publisher.post(ItemEventFactory.createTimeSeriesEvent(
                    "JDBC_NonForecast_Probe", series, "hex-isolated-qualification"));
        } finally {
            context.ungetService(reference);
        }
    }

    @Override
    public void stop(BundleContext context) {
    }
}
