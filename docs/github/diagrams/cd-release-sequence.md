# CD Release - Sequence Diagram

Sequence diagram for CD release creation and packaging.

```mermaid
sequenceDiagram
  actor Dev
  participant GitHub
  participant ReleaseWorkflow as Release_please_workflow
  participant BuildWorkflow as Build_package_workflow
  participant ReleasePlease as release_please_action
  participant GHReleases as GitHub_Releases

  Dev->>GitHub: Push commit to main
  GitHub->>ReleaseWorkflow: Trigger CD Release workflow

  ReleaseWorkflow->>ReleasePlease: Run release-please-action with config/manifest
  ReleasePlease-->>ReleaseWorkflow: Outputs release_created, tag_name, version

  alt Release created
    ReleaseWorkflow-->>BuildWorkflow: needs release-please with release_created == true
    GitHub->>BuildWorkflow: Start build-package job

    BuildWorkflow->>GitHub: Checkout repository at tag_name
    BuildWorkflow->>BuildWorkflow: Install uv, Python, build dependency
    BuildWorkflow->>BuildWorkflow: Build distribution artifacts (dist/*)
    BuildWorkflow->>GHReleases: Upload dist/* to release tag
    BuildWorkflow->>GitHub: Upload dist/ as workflow artifact
  else No release created
    ReleaseWorkflow-->>Dev: No new release (no changes or already released)
  end
```

## Related Files

- `.github/workflows/cd-release.yml`
- `release-please-config.json`
- `.release-please-manifest.json`
