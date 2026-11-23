# Security policy

## Reporting a vulnerability

Please report a security problem in FiberQ privately, by e-mail to
vukovicvl@fiberq.net, not in a public issue. Say which versions of FiberQ and
QGIS you use, what the problem is and how to reproduce it; a sample project
helps, if you can share one.

You will get an answer as soon as possible, normally within a week. Once a fix
is released, the problem can be made public, with credit to you if you want it.

## Supported versions

Security fixes go into a new release of FiberQ, which the QGIS Plugin Manager
offers as an update. Only the latest release gets them.

| Version | Security fixes |
|---|---|
| The latest release | yes |
| Any earlier release | no |

## Scope

The plugin in `fiberq/`, as its releases are published (on plugins.qgis.org and
on the forges' release pages), and the pipeline that tests and packages it: the
scripts in `ci/` and the forge configurations that run them
(`.github/workflows/ci.yml`, `.gitlab-ci.yml`). A problem in QGIS itself
belongs to the QGIS project.
