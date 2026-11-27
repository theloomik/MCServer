# Usability and accessibility checklist (M4-QA-03)

Run this on every M4 build that goes to testers, on a real Windows desktop (not
offscreen). It covers what automated tests cannot see. The automated part runs
with the unit tests in `tests/unit/presentation/test_accessibility.py`:

- every control has an accessible name;
- every control can be reached with Tab;
- WCAG AA contrast of the theme colours;
- focus styles exist;
- keyboard shortcuts work;
- the window's minimum size at 125 %/150 % scaling, in English and Ukrainian.

Copy the sign-off table at the end into the release notes or PR, fill it in,
and keep any failures as issues.

## Before you start

- Build or run MCServer from the commit under test: `python -m mcserver`.
- Prepare a test machine with **Java 21** and **one without Java** (or rename
  `java.exe` temporarily) so both Java states can be seen.
- Delete or rename `mcserver_settings.json` in the servers folder to see the
  first-run guide, and keep a copy to restore afterwards.
- Never test on a server whose world matters: use copies.

## 1. Keyboard only

Unplug or ignore the mouse for this section.

| # | Check | Expected |
| --- | --- | --- |
| K1 | Start MCServer with no servers | The setup guide opens with the focus inside it; Tab moves through its buttons; Enter on **Next** advances; **Esc** skips the guide |
| K2 | **Ctrl+L** | Focus moves to the server list; arrow keys change the selected server |
| K3 | **Ctrl+1 … Ctrl+4** | Overview, Properties, Worlds, Backups open in that order |
| K4 | **Ctrl+K** | Overview opens and the console command line has the focus (or the console text when the server is stopped) |
| K5 | Tab through the whole window | Every button, field, list and table is reached; the focused control always shows a light-blue border or highlight |
| K6 | **Ctrl+N** | The Create server dialog opens with the focus in **Name**; the memory slider moves with the arrow keys |
| K7 | Fill the Create form with the keyboard only (Tab, Space for the EULA box, Enter) | The server is created; a success notification appears |
| K8 | **Esc** in any dialog (Create, Edit, Delete, Details…) and on the Settings page | It closes and the focus returns to where it was before; while a dialog is open the window behind it cannot be used |
| K9 | Server actions beside the tabs (Open folder, Logs, Edit, Delete) with Tab and Enter | Each is reached and named by Narrator; Delete asks first |
| K10 | **Ctrl+,** | Settings open |
| K11 | Start (**Ctrl+R**), stop and restart a server with the keyboard | Works; no step needs the mouse |
| K12 | A long operation (backup) with the keyboard | Tab reaches **Cancel** in the progress row; Space cancels |
| K13 | Notifications | When a toast appears, it does not take the focus. Its close button and **Details** can be reached with Tab |

## 2. Screen reader (Windows Narrator)

Start Narrator with **Ctrl+Win+Enter**.

| # | Check | Expected |
| --- | --- | --- |
| N1 | Move through the server list | Each server is read with its name and state |
| N2 | Console command field, console output, console filter | Each is read with its name, not as "edit" or "combo box" alone |
| N3 | Fields on Create, Edit, Settings, Adopt, Download, Prompt | Each field is read with its label; fields with a hint read the hint as the description |
| N4 | Icon-only buttons (refresh, add, copy address, close notification) | Each is read with its tooltip text |
| N5 | Server properties | Each editor is read with the property name (e.g. "max-players") |
| N6 | Error notifications | The text is read; **Details** is announced as a button |

## 3. Display scaling

Windows Settings › System › Display › Scale. Sign out and in again if Windows
asks to.

| # | Check | Expected |
| --- | --- | --- |
| S1 | 125 % on a 1366 × 768 screen, maximised | Everything visible without horizontal scrolling; header buttons not cut off |
| S2 | 150 % on a 1920 × 1080 screen | Same as S1 |
| S3 | Make the window as narrow as Windows allows at 150 % | The four stat tiles form a 2 × 2 grid; the backup schedule wraps onto two lines; nothing overlaps |
| S4 | Icons and the status dots at 125 % and 150 % | Sharp, not blurry, not cut off |
| S5 | Pages (Create, Settings, setup guide) at 150 % | The page scrolls when it is taller than the window; buttons stay reachable |

## 4. Ukrainian strings

Settings › Language › Українська (the window switches without a restart).

| # | Check | Expected |
| --- | --- | --- |
| U1 | Every tab of the dashboard at 100 %, 125 %, 150 % | No text cut off in buttons, tabs, captions or stat tiles |
| U2 | Setup guide, Create, Settings, Adopt, Download, Delete pages | Labels and hints wrap instead of being cut off |
| U3 | Plurals: 1, 2, 5, 11, 21 backups or servers where counts appear | The right form (сервер / сервери / серверів) |
| U4 | Notifications with long texts | Wrapped inside the toast, close button still visible |
| U5 | Keyboard shortcuts (Ctrl+N, Ctrl+R, Ctrl+, , F5, Ctrl+1…4, Ctrl+L, Ctrl+K) with the Ukrainian layout active | Each works; none is taken by an open dialog |

## 5. Contrast and colour

| # | Check | Expected |
| --- | --- | --- |
| C1 | Hints, captions and stat tiles on a dim or glossy laptop screen | Readable |
| C2 | Windows contrast themes (Settings › Accessibility › Contrast themes) | Note how MCServer looks (not verified yet); every text must stay readable. Report anything that is not |
| C3 | Status is never shown by colour alone | Every coloured dot has a text next to it (Running, Stopped…) |

## Sign-off

| Build / commit | Date | Tester | Keyboard | Narrator | Scaling | Ukrainian | Contrast | Notes / issues |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  | ☐ | ☐ | ☐ | ☐ | ☐ |  |

## Mouse wheel (UX overhaul)

| # | Check | Expected |
| --- | --- | --- |
| W1 | Scroll Settings and server Properties with the wheel while the pointer passes over number fields and drop-downs | The page scrolls; no value changes |
| W2 | Click into a number field, then turn the wheel | Now the value changes (on purpose) |
