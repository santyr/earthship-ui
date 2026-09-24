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

/** Synthetic daily forecast series only in the disconnected JDBC fixture. */
public final class HexForecastDailyProbe implements BundleActivator {
    private static void publish(EventPublisher publisher, String item, Instant first, int kind) {
        TimeSeries series = new TimeSeries(TimeSeries.Policy.REPLACE);
        for (int index = 0; index < 7; index++) {
            Instant at = first.plusSeconds(index * 86400L);
            if (kind == 0) {
                series.add(at, new QuantityType<>(Double.toString((index + 1) / 10.0) + " in"));
            } else if (kind == 1) {
                series.add(at, new DecimalType(Double.toString((index + 1) / 10.0)));
            } else if (kind == 2) {
                series.add(at, new DecimalType(Integer.toString(60 + index)));
            } else {
                series.add(at, new DecimalType(Double.toString(2 + index / 10.0)));
            }
        }
        publisher.post(ItemEventFactory.createTimeSeriesEvent(
                item, series, "hex-isolated-forecast-daily"));
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
            publish(publisher, "Forecast_Daily_PrecipSum", first, 0);
            publish(publisher, "Forecast_Daily_PrecipProbMax", first, 1);
            publish(publisher, "Forecast_Daily_WeatherCode", first, 2);
            publish(publisher, "Forecast_Daily_UVIndex", first, 3);
        } finally {
            context.ungetService(reference);
        }
    }

    @Override
    public void stop(BundleContext context) {
    }
}
