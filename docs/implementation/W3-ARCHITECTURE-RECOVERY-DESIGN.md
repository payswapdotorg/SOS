# W3 Architecture Recovery Design

W3 treats an existing repository as a source of static evidence, not as a complete description of runtime reality.

## Recovery rule

`repository facts → graph facts` only when the relationship is directly supported by deterministic source inspection. Everything else remains explicitly unknown or unavailable.

## Supported static signals

- source files become `COMPONENT` nodes;
- Python imports become `DEPENDENCY` edges only when the imported module resolves to another discovered repository file;
- common manifests and deployment/configuration filenames become conservative `POLICY` or `DEPLOYMENT` nodes;
- every recovered node and edge stores source-path and repository-revision provenance in its attributes.

## Truthfulness

Static discovery does not establish runtime behavior. The report therefore emits explicit unavailable findings for runtime environment and live deployment facts rather than synthesizing them.

## Determinism

The adapter sorts paths, imports, nodes and edges and never embeds filesystem discovery order in the result. Identical repository bytes plus the same supplied revision identifier produce the same semantic report.

## Non-scope

No runtime telemetry, causal inference, candidate generation, graph mutation, assurance, promotion or experimentation is performed by W3.
