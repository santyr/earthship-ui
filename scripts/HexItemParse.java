// Offline check of the next observational Item; never loads the live registry.
import java.nio.file.Path;
import org.openhab.core.model.ItemsStandaloneSetup;
import org.eclipse.xtext.resource.XtextResourceSet;
import org.eclipse.emf.common.util.URI;

public class HexItemParse {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("one items file required");
        var injector = new ItemsStandaloneSetup().createInjectorAndDoEMFRegistration();
        var resources = injector.getInstance(XtextResourceSet.class);
        var resource = resources.getResource(URI.createFileURI(Path.of(args[0]).toAbsolutePath().toString()), true);
        if (!resource.getErrors().isEmpty()) throw new IllegalStateException(resource.getErrors().toString());
        var model = resource.getContents().get(0);
        var children = model.eAllContents();
        int count = 0;
        while (children.hasNext()) {
            var child = children.next();
            if (!child.eClass().getName().equals("ModelItem")) continue;
            count++;
            for (String key : new String[]{"name", "type", "label", "groups"}) {
                var feature = child.eClass().getEStructuralFeature(key);
                if (feature == null) throw new IllegalStateException("missing " + key);
                System.out.println(key + "=" + child.eGet(feature));
            }
        }
        if (count != 1) throw new IllegalStateException("expected exactly one Item");
        System.out.println("syntax_errors=0");
    }
}
