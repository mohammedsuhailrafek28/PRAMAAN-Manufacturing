// Disposable library invocation. No recall decisions, engine code or server.
import java.nio.file.*;
import java.io.*;
import java.util.*;
import io.openepcis.eventhash.EventHashGenerator;

class Probe {
    public static void main(String[] args) throws Exception {
        for (String path : args) try (InputStream in = Files.newInputStream(Path.of(path))) {
            var hashes = new EventHashGenerator().fromJson(in, "sha-256")
                .collect().asList().await().atMost(java.time.Duration.ofSeconds(30));
            System.out.println("DOC=" + Path.of(path).getFileName());
            System.out.println("EVENT_COUNT=" + hashes.size());
            for (var hash : hashes) System.out.println("HASH=" + hash);
            if (hashes.size() != 6) throw new AssertionError("Expected six event hashes");
        }
        System.exit(0); // Dispose library scheduler threads with this one-shot probe.
    }
}
