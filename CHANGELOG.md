# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v2.0.2 - 2025-01-22

### Fixed

- Resolved case sensitivity issue in document type extension checks.
- Fixed channel-related issues for mirror and leech operations.
- Addressed the issue where thumbnails were removed after a restart.

## v2.0.1 - 2025-01-20

### Fixed

- Token generation issues caused by the command suffix.

### Removed

- The "refresh status" and "overview status" buttons, simplifying the status interface.

## v2.0.0 - 2025-01-18

### Breaking Changes

- Rebased the project on the latest MLTB version.

### Added

- Integrated all new features from MLTB, excluding NZB and jDownloader.
- Introduced watermark support for videos.
- Enabled the ability to use a user session string to download private media from Telegram.
- Reintroduced RSS feed support.
- Added versioning system.
- Added `CHANGELOG.md` to track changes.

### Removed

- Removed certain limit-related variables such as `MIRROR LIMIT` and `LEECH LIMIT`.
