import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;

import org.openhab.core.events.EventPublisher;
import org.openhab.core.items.events.ItemEventFactory;
import org.openhab.core.library.types.DecimalType;
import org.openhab.core.library.types.QuantityType;
import org.openhab.core.types.TimeSeries;
import org.osgi.framework.BundleActivator;
import org.osgi.framework.BundleContext;
import org.osgi.framework.ServiceReference;

/** Synthetic series only inside the disconnected OpenHAB/JDBC fixture. */
public final class HexForecastMeteorologyProbe implements BundleActivator {
    private static void publish(EventPublisher publisher, String item, Instant first, int kind) {
        TimeSeries series = new TimeSeries(TimeSeries.Policy.REPLACE);
        for (int index = 0; index < 48; index++) {
            Instant at = first.plusSeconds(index * 3600L);
            if (kind == 0) {
                series.add(at, new DecimalType(Double.toString(index / 100.0)));
            } else if (kind == 1) {
                series.add(at, new QuantityType<>(Integer.toString(100 + index) + " W/m²"));
            } else {
                series.add(at, new DecimalType(Double.toString(index / 1000.0)));
            }
        }
        publisher.post(ItemEventFactory.createTimeSeriesEvent(
                item, series, "hex-isolated-forecast-meteorology"));
    }

    @Override
    public void start(BundleContext context) throws Exception {
        if (!"1".equals(System.getenv("HEX_JDBC_ISOLATED"))) {
            throw new IllegalStateException("isolated fixture guard missing");
        }
        Instant first = Instant.parse(Files.readString(
                Path.of("/tmp/hex-forecast-temperature-first")).trim());
        if (!first.isAfter(Instant.now().plusSeconds(3600))) {
            throw new IllegalArgumentException("forecast target must be future");
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
            publish(publisher, "Forecast_Cloudiness", first, 0);
            publish(publisher, "Forecast_Radiation", first, 1);
            publish(publisher, "Forecast_PrecipProb", first, 2);
        } finally {
            context.ungetService(reference);
        }
    }

    @Override
    public void stop(BundleContext context) {
    }
}
