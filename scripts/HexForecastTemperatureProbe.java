import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;

import org.openhab.core.events.EventPublisher;
import org.openhab.core.items.events.ItemEventFactory;
import org.openhab.core.library.types.QuantityType;
import org.openhab.core.types.TimeSeries;
import org.osgi.framework.BundleActivator;
import org.osgi.framework.BundleContext;
import org.osgi.framework.ServiceReference;

/** Synthetic forecast-series events only inside the disconnected JDBC fixture. */
public final class HexForecastTemperatureProbe implements BundleActivator {
    private static void publish(EventPublisher publisher, String item, Instant first,
            int count, long stepSeconds, int base) {
        TimeSeries series = new TimeSeries(TimeSeries.Policy.REPLACE);
        for (int index = 0; index < count; index++) {
            series.add(first.plusSeconds(index * stepSeconds),
                    new QuantityType<>(Integer.toString(base + index) + " °F"));
        }
        publisher.post(ItemEventFactory.createTimeSeriesEvent(
                item, series, "hex-isolated-forecast-temperature"));
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
            publish(publisher, "Forecast_Temp", first, 48, 3600, 40);
            publish(publisher, "Forecast_Daily_High", first, 7, 86400, 70);
            publish(publisher, "Forecast_Daily_Low", first, 7, 86400, 30);
        } finally {
            context.ungetService(reference);
        }
    }

    @Override
    public void stop(BundleContext context) {
    }
}
