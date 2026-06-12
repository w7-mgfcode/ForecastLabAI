// E2 (#408) — single source for the workspace-name client validation,
// shared by the showcase run controls and the WorkspaceEditDialog. Mirrors
// the backend DemoRunRequest.workspace_name pattern (app/features/demo/
// schemas.py): lowercase letters/digits, then -/_ allowed; ≤100 chars.
export const WORKSPACE_NAME_PATTERN = /^[a-z0-9][a-z0-9\-_]*$/

export const WORKSPACE_NAME_HINT =
  'Lowercase letters/digits only, then “-” or “_” (must not start with either).'
