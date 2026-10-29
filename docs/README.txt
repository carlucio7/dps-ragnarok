DPS Ragnarok {VERSION} — DPS meter for Ragnarok Online (ROLatam)
================================================================

A small widget that shows your DPS and the party's damage ranking in real time
by reading the game's own replay recording. It also has a full analysis window
(per player, per monster, timeline, buffs, deaths, build tests) and the "Snitch"
tab, which points out what was missing in boss fights.

Languages: português, English, español (right-click › Language).


HOW TO USE
----------
1. Extract the .zip into a folder of your own (e.g. Documents\DpsRagnarok).
2. Run DpsRagnarok.exe. No installation or administrator rights needed.
3. In the game, start recording a replay. The meter finds the recording by
   itself and starts counting.
4. Right-click the widget for all options. The chart button opens the full
   analysis.

IF THE GAME IS NOT IN C:\Gravity\Ragnarok
The meter looks for the game folder by itself (in the Windows registry and on
your drives). If the middle of the widget says "I couldn't find the game's
Replay folder", click there and pick the Ragnarok folder (the one with
Ragexe.exe and data.grf) or the Replay folder inside it. You can change it later
in: right-click › Replay folder. With several game installations, it watches all
Replay folders and follows the newest recording.

You can also open a recorded replay: right-click › Open saved replay, or drag
the .rrf file onto DpsRagnarok.exe.

Tip for the Snitch tab: start recording before the party buffs up. Other
players' buffs that were already active when the recording started only show up
when they end.


SAFETY
------
- The program only reads: the .rrf files in the game's Replay folder, the name
  tables in the game's data.grf (to show the names of new monsters, like the
  ones in the Varmundt Biosphere) and, in the Windows registry, where the game
  was installed. It changes none of these, does not read game memory, inject
  anything, capture network packets or access the internet.
- It only writes its own settings, saved tests and a name cache to
  %APPDATA%\RODpsMeter.
- The program is not digitally signed, so Windows may show "Windows protected
  your PC". Before allowing it, check that the file is the original: open
  PowerShell in the folder and run

      Get-FileHash .\DpsRagnarok.exe

  The code shown must match the one in SHA256.txt (and on the page you
  downloaded from). If it matches, click "More info" › "Run anyway".
- Only download from the official link. Don't accept a loose .exe from someone
  else without checking the code.
- This is not an official Gravity or ROLatam program. Use at your own risk.


IF THE PROGRAM DOESN'T OPEN
---------------------------
- DpsRagnarok.exe is gone from the folder, or Windows says "Windows cannot access
  the specified device, path, or file": your antivirus deleted it (a false alarm,
  common with unsigned programs). Check the .exe code as explained above and
  restore the file in Windows Security › Virus & threat protection › Protection
  history (or in your antivirus quarantine). Then add the program folder as an
  exclusion.
- "The ordinal 380 could not be located": this happened up to version 1.0.2.
  Download the latest version.


UNINSTALL
---------
Delete the program folder and the %APPDATA%\RODpsMeter folder.


LIMITS
------
- Only the damage your client receives is shown: players off screen don't count.
- Skill, buff, monster and item names come from the installed game, in the
  chosen language. Without the game on the PC, the program uses a copy that may
  be out of date; monster skills the game doesn't name get an approximate name.
- With several clients recording at once, the meter follows the newest recording
  (you can open another one manually).
