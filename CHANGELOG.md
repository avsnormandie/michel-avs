# Changelog

All notable changes to Michel (AVS fork of Clawdbot) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- AVS-specific customizations planned:
  - Tool Result Limiter
  - /compact manual command

## [0.3.0] - 2026-02-05

### Added

- AVS Response Forwarder
- Direct SSH endpoint

## [0.2.0] - 2026-02-04

### Added

- `avs-compaction-guard.ts` - Extension de sauvegarde automatique vers la KB AVS
  - Intercepte `session_before_compact`
  - Extrait le contexte important (requetes utilisateur, decisions)
  - Sauvegarde vers la base de connaissances AVS
  - Envoie notification Telegram avant compaction
  - Listage des fichiers modifies/lus

### Changed

- Moved Compaction Guard from planned to implemented

## [0.1.0] - 2026-02-04

### Added

- Fork created from clawdbot/clawdbot
- CHANGELOG.md for version tracking
- MICHEL.md for AVS-specific documentation

### Changed

- Repository renamed to michel-avs
- Description updated for AVS Technologies

[Unreleased]: https://github.com/avsnormandie/michel-avs/compare/avs-0.3.0...HEAD
[0.3.0]: https://github.com/avsnormandie/michel-avs/compare/avs-0.2.0...avs-0.3.0
[0.2.0]: https://github.com/avsnormandie/michel-avs/compare/avs-0.1.0...avs-0.2.0
[0.1.0]: https://github.com/avsnormandie/michel-avs/releases/tag/avs-0.1.0
