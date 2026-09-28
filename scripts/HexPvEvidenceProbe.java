import java.time.ZonedDateTime;

import org.openhab.core.items.Item;
import org.openhab.core.items.ItemRegistry;
import org.openhab.core.persistence.extensions.PersistenceExtensions;
import org.osgi.framework.BundleActivator;
import org.osgi.framework.BundleContext;
import org.osgi.framework.ServiceReference;

/** Isolated-only explicit JDBC writer for the PV evidence exclusion rehearsal. */
public final class HexPvEvidenceProbe implements BundleActivator {
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
            Item item = registry.getItem("MPPT60_PV_Day_Evidence_JSON");
            PersistenceExtensions.persist(item, ZonedDateTime.now(),
                "{\"isolatedQualification\":\"explicit-pv-writer\"}", "jdbc");
        } finally {
            context.ungetService(reference);
        }
    }

    @Override
    public void stop(BundleContext context) {
    }
}
