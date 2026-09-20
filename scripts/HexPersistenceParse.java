// Offline syntax/selector check using the installed OpenHAB parser.
// Does not register a persistence service or verify runtime strategy resolution.
import java.nio.file.Path;
import org.openhab.core.model.persistence.PersistenceStandaloneSetup;
import org.eclipse.xtext.resource.XtextResourceSet;
import org.eclipse.xtext.nodemodel.util.NodeModelUtils;
import org.eclipse.emf.common.util.URI;

public class HexPersistenceParse {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("one .persist file required");
        var injector = new PersistenceStandaloneSetup().createInjectorAndDoEMFRegistration();
        var resources = injector.getInstance(XtextResourceSet.class);
        var resource = resources.getResource(
            URI.createFileURI(Path.of(args[0]).toAbsolutePath().toString()), true);
        if (!resource.getErrors().isEmpty())
            throw new IllegalStateException(resource.getErrors().toString());
        if (resource.getContents().size() != 1) throw new IllegalStateException("missing model");
        var model = resource.getContents().get(0);
        if (!model.eClass().getName().equals("PersistenceModel"))
            throw new IllegalStateException("wrong model type");
        var children = model.eAllContents();
        while (children.hasNext()) {
            var child = children.next();
            if (child.eClass().getName().equals("PersistenceConfiguration")) {
                var strategies = NodeModelUtils.findNodesForFeature(child,
                    child.eClass().getEStructuralFeature("strategies"));
                System.out.println("strategy_tokens=" + strategies.stream()
                    .map(n -> n.getText().trim()).toList());
            } else {
                System.out.println("selector_type=" + child.eClass().getName());
            }
        }
        System.out.println("syntax_errors=0");
    }
}
