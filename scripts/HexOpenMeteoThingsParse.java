// Offline grammar check only: never starts a provider or contacts OpenMeteo.
import java.nio.file.Path;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.openhab.core.model.thing.ThingStandaloneSetup;
import org.eclipse.xtext.resource.XtextResourceSet;
import org.eclipse.emf.common.util.URI;

public class HexOpenMeteoThingsParse {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("one .things file required");
        var injector = new ThingStandaloneSetup().createInjectorAndDoEMFRegistration();
        var resources = injector.getInstance(XtextResourceSet.class);
        var resource = resources.getResource(URI.createFileURI(Path.of(args[0]).toAbsolutePath().toString()), true);
        if (!resource.getErrors().isEmpty()) throw new IllegalStateException("Thing syntax rejected: " + resource.getErrors());
        if (resource.getContents().size() != 1) throw new IllegalStateException("missing Thing model");
        var model = resource.getContents().get(0);
        if (!model.eClass().getName().equals("ThingModel")) throw new IllegalStateException("wrong model");
        if (model.eContents().size() != 3) throw new IllegalStateException("expected bridge and two child Things");
        System.out.println("model=ThingModel");
        System.out.println("declarations=3");
        var invalid = resources.createResource(URI.createURI("inmemory:/invalid.things"));
        invalid.load(new ByteArrayInputStream("Bridge [".getBytes(StandardCharsets.UTF_8)), Map.of());
        if (invalid.getErrors().isEmpty()) throw new IllegalStateException("malformed Thing accepted");
        System.out.println("negative_syntax_rejected=true");
        System.out.println("syntax_errors=0");
    }
}
