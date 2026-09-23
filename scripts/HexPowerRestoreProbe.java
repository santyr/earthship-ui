import java.time.ZonedDateTime;

import org.openhab.core.items.Item;
import org.openhab.core.items.ItemRegistry;
import org.openhab.core.persistence.extensions.PersistenceExtensions;
import org.osgi.framework.BundleActivator;
import org.osgi.framework.BundleContext;
import org.osgi.framework.ServiceReference;

/** Exercises the production explicit JDBC writer API inside the isolated fixture. */
public final class HexPowerRestoreProbe implements BundleActivator {
    @Override
    public void start(BundleContext context) throws Exception {
        if (!"1".equals(System.getenv("HEX_JDBC_ISOLATED"))) {
            throw new IllegalStateException("isolated fixture guard missing");
        }
        ServiceReference<ItemRegistry> reference = context.getServiceReference(ItemRegistry.class);
        if (reference == null) {
            throw new IllegalStateException("Item registry unavailable");
        }
        ItemRegistry registry = context.getService(reference);
        if (registry == null) {
            throw new IllegalStateException("Item registry service unavailable");
        }
        try {
            Item item = registry.getItem("Power_Evidence_JSON");
            String state = "{\"isolatedQualification\":\"explicit-writer\"}";
            PersistenceExtensions.persist(item, ZonedDateTime.now(), state, "jdbc");
        } finally {
            context.ungetService(reference);
        }
    }

    @Override
    public void stop(BundleContext context) {
    }
}
