# Repository Conventions (cex)

## Execution & Verification
- **Build/Test/Lint:** No explicit build/test/lint commands were found in the initial scan. Please confirm the correct commands for running tests, linting, or building the project.
- **Local Testing:** To verify changes, the primary method is running the application locally and manually testing functionality (e.g., opening `index.html` in a browser).

## Architecture & Structure
- **Project Type:** Static website built with plain HTML, CSS, and JavaScript.
- **Data Storage:** Journal entries are stored locally using the browser's `localStorage` in `script.js`. There is no backend/database involved.
- **Entry Point:** `index.html` is the main entry point.

## Workflow Gotchas
- **File Dependency:** `script.js` relies on `localStorage` for persistence.
- **Styling:** All styling is contained in `style.css`.

## Commands to Know
- To run/test: Open `index.html` in a browser.
- To modify: Edit `index.html`, `style.css`, or `script.js`.