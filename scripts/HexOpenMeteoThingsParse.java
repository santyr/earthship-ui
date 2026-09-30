// Offline grammar check only: never starts a provider or executes a command.
import java.nio.file.Path;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.openhab.core.model.thing.ThingStandaloneSetup;
import org.eclipse.xtext.resource.XtextResourceSet;
import org.eclipse.emf.common.util.URI;

public class HexOpenMeteoThingsParse {
    public static void main(String[] args) throws Exception {
        if (args.length != 1 && args.length != 2)
            throw new IllegalArgumentException("one .things file and optional declaration count required");
        int expected = args.length == 2 ? Integer.parseInt(args[1]) : 3;
        if (expected < 1 || expected > 16)
            throw new IllegalArgumentException("bounded declaration count required");
        var injector = new ThingStandaloneSetup().createInjectorAndDoEMFRegistration();
        var resources = injector.getInstance(XtextResourceSet.class);
        var resource = resources.getResource(URI.createFileURI(Path.of(args[0]).toAbsolutePath().toString()), true);
        if (!resource.getErrors().isEmpty()) throw new IllegalStateException("Thing syntax rejected: " + resource.getErrors());
        if (resource.getContents().size() != 1) throw new IllegalStateException("missing Thing model");
        var model = resource.getContents().get(0);
        if (!model.eClass().getName().equals("ThingModel")) throw new IllegalStateException("wrong model");
        if (model.eContents().size() != expected)
            throw new IllegalStateException("unexpected Thing declaration count");
        System.out.println("model=ThingModel");
        System.out.println("declarations=" + expected);
        var invalid = resources.createResource(URI.createURI("inmemory:/invalid.things"));
        invalid.load(new ByteArrayInputStream("Bridge [".getBytes(StandardCharsets.UTF_8)), Map.of());
        if (invalid.getErrors().isEmpty()) throw new IllegalStateException("malformed Thing accepted");
        System.out.println("negative_syntax_rejected=true");
        System.out.println("syntax_errors=0");
    }
}
