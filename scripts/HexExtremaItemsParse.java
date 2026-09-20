// Offline grammar check only: no live provider, registry, persistence or device access.
import java.nio.file.Path;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.openhab.core.model.ItemsStandaloneSetup;
import org.eclipse.xtext.resource.XtextResourceSet;
import org.eclipse.emf.common.util.URI;

public class HexExtremaItemsParse {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("one .items file required");
        var injector = new ItemsStandaloneSetup().createInjectorAndDoEMFRegistration();
        var resources = injector.getInstance(XtextResourceSet.class);
        var resource = resources.getResource(URI.createFileURI(Path.of(args[0]).toAbsolutePath().toString()), true);
        if (!resource.getErrors().isEmpty()) throw new IllegalStateException("Item syntax rejected");
        if (resource.getContents().size() != 1) throw new IllegalStateException("missing Item model");
        var model = resource.getContents().get(0);
        if (!model.eClass().getName().equals("ItemModel")) throw new IllegalStateException("wrong model");
        for (var item : model.eContents()) {
            var name = item.eClass().getEStructuralFeature("name");
            if (name == null) throw new IllegalStateException("unnamed Item");
            System.out.println("item=" + item.eGet(name));
        }
        var invalid = resources.createResource(URI.createURI("inmemory:/invalid.items"));
        invalid.load(new ByteArrayInputStream("Number:Temperature".getBytes(StandardCharsets.UTF_8)), Map.of());
        if (invalid.getErrors().isEmpty()) throw new IllegalStateException("malformed Item accepted");
        System.out.println("negative_syntax_rejected=true");
        System.out.println("syntax_errors=0");
    }
}
