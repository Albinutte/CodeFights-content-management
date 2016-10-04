# CodeFights content management plugin
Sublime plugin for CodeFights content team.

**Installation:** 
Download repository as a `CodeFights-content-management` folder and move it into your Packages folder (the one that opens by `Preferences -> Browse Packages`). Alternatively, checkout the repository into your Packages folder (this way it will be easier to update it).

Restart Sublime if it was open.

**Usage:**
 * `ctrl+shift+c`:
  * from `<task>.<ext>`: launches validator on current snippet;
  * from `README.md`: launches validator on all snippets;
  * from `meta.json`: launches outputs generator with `-r` flag;
  * from `tests`: launches tests generator with `-o` flag;
 * `ctrl+shift+m`:
  * from `<task>.py`: launches auto bugfixes with validation;
  * from `README.md`: launches limits getter with `--upd` flag;
 * `ctrl+shift+h`:
  * from `<task>.<ext>`: launches code style checker on current snippet;
  * from `README.md`: launches code style checker on all snippets;
 * `ctrl+d`: kills current process

*Key bindings can be changed from preferences.*

More commands are available from Tools -> CodeFights.
