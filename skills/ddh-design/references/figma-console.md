# Figma Console execution

Use this route when the task needs Figma nodes, tokens, components or a rendered Figma result and the Console provider is configured.

Select the available provider by the required operation and its qualified tool name. Preserve provider identity for subsequent reads and writes. Existing Figma connector authorization does not supply Console credentials or a Desktop Bridge connection.

Start with the provider's status tool, such as figma_get_status. Confirm the intended file and Bridge. Read the target nodes and existing system before a change. Observe project authority and the user's scope for Figma writes. Read back the changed target and inspect a screenshot from the same file and state.

On a timeout, transport failure or error after a mutation, re-read the target before retrying. The upstream identity wrapper can return an error after Figma changes have already happened. A repeated create can produce duplicates.

For missing access or unavailable tools, report what is needed and continue independent work. The integration setup is a separate explicit host action. Desktop Bridge operations and cloud or read-only transports have different capabilities.

Pinned source and setup templates ship in the optional figma-console integration of DDH. [Upstream source](https://github.com/southleft/figma-console-mcp/tree/5ef4df3791606b8e1f877557ec0dde4796250b44).
