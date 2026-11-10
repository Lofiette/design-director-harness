# DeepSeek Harness adapter

Install DDH into the project with `node tools/ddh.mjs install --project <project>` from the shared distribution. It adds the CPT runtime, intake guidance and skills under `.agents/skills`. Open a fresh DSH session in the project and confirm that the active preset exposes the filesystem skill provider.

The adapter export uses `.dsh/skills` for isolated provider tests. Check the discovered catalog for shadowing when the active preset mounts its own provider.

For an authorized independent review, use the host's fresh-context child tool. If the host returns the result on a later turn, checkpoint the review brief and wait for that event. Verify the active pruning configuration and reload any instruction marked as pruned before a consequential action.

This bundle has no Cordis hooks or bundled services. The DSH desktop shell, reflection and model-router packages remain native integrations.
