// Which version of FOSIT this page runs, and its review status. Reviewers and users can match the engine fingerprint and the
// commit with the repository (web/scripts/build_core_bundle.py writes both into fosit-core.json at build time).
import { useEffect, useState } from "react";
import { APP_VERSION, REPO_URL } from "../config";

type Manifest = { sha256?: string; commit?: string | null; dirty?: boolean | null };

export function VersionNote() {
  const [m, setM] = useState<Manifest | null>(null);
  useEffect(() => {
    fetch(new URL("./fosit-core.json", document.baseURI)).then((r) => r.json()).then(setM).catch(() => setM(null));
  }, []);
  return (
    <p className="disclosure" data-testid="version-note">
      FOSIT {APP_VERSION}, pre-release, not yet independently reviewed
      {m?.sha256 && <> · engine <code>{m.sha256.slice(0, 8)}</code></>}
      {m?.commit && <> · commit <a href={`${REPO_URL}/commit/${m.commit}`} target="_blank" rel="noreferrer"><code>{m.commit.slice(0, 7)}</code></a></>}
      {m?.dirty && " (with uncommitted changes)"}
    </p>
  );
}
