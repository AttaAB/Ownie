# Demo: a ownie review, start to finish

A real review session on a small expense-splitting API
(Flask + SQLite, ~490 lines) that a fresh AI agent vibe-coded from a
one-paragraph prompt, with no design steering.

How this was recorded, so you know what's real:

- The questions, code, hints, explanations and **every grade** are real
  model output, graded live.
- The answers were typed for the demo (by Claude, playing a developer
  who half-knows the code) to show each path: a strong answer, a vague
  one that gets a hint and a retry, and one that asks for the explanation.
- The decisions come from one earlier run of the same extraction on the
  same commit, reused so the answers could be written against them.

Things to notice:

- Question 1 is **owned**: the answer names the central consequence (no
  authentication, and `GET /groups` lists every ID).
- Question 2 goes **partial → hint → owned**. In an earlier take, an
  answer claiming "anyone can run Python on the server" was graded *not
  quite*, because Werkzeug's debugger is PIN-protected: the grader reads
  the code and doesn't reward overstatement.
- Question 3 ends with **e** (explain): the answer key is shown, and the
  decision is kept for `ownie review --revisit`.

> Recorded before the project was renamed from Engineering Mentor to
> Ownie, so the transcript shows the old `mentor` command (now `ownie`)
> and predates Ownie the robot.

```text
$ mentor review --all

Found 11 design decisions in whole project
Here are the 3 you'd most likely be asked to explain.

╭─  security · splitter/app.py:139-253  ───────────────────────────────────────────╮
│                                                                                  │
│    139     @app.post("/groups")                                                  │
│    140     def create_group():                                                   │
│    141         name = required_name(body())                                      │
│    142         db = get_db()                                                     │
│    143         cur = db.execute("INSERT INTO groups (name) VALUES (?)", (name,)  │
│    144         db.commit()                                                       │
│    145         return jsonify(id=cur.lastrowid, name=name, members=[]), 201      │
│    146                                                                           │
│    147     @app.get("/groups")                                                   │
│    148     def list_groups():                                                    │
│    149         rows = get_db().execute("SELECT id, name FROM groups ORDER BY id  │
│    150         return jsonify([dict(r) for r in rows])                           │
│    151                                                                           │
│    152     @app.get("/groups/<int:group_id>")                                    │
│                                                                                  │
│  The routes operate on groups identified only by an integer path parameter and   │
│  do not inspect an authenticated principal.                                      │
│                                                                                  │
│  Q  A stranger who knows or guesses a group ID sends GET and POST requests to    │
│     that group. Walk through which data they can read and which records they     │
│     can create or change, and identify what in this code limits their access to  │
│     a particular group.                                                          │
│                                                                                  │
╰──────────────────────────────────────────────────────────────────────────  1/3  ─╯
  Type your answer, or  h hint · e explain · s skip · q quit
› Nothing limits them — there's no authentication at all. GET /groups lists every 
group, so they don't even need to guess an ID. They can read any group's members, 
expenses and balances, and POST new members and expenses to it. The only checks are 
that the group and member IDs exist.
  ✓ Owned      You correctly identify the lack of authentication or authorization   
               and that anyone can enumerate groups, read their data, and add       
               members or expenses. The only scoping is referential validation      
               that the group and member IDs exist; there are no update/delete      
               operations or ownership/audit checks.                                

╭─  security · run.py:4-5  ────────────────────────────────────────────────────────╮
│                                                                                  │
│    4 if __name__ == "__main__":                                                  │
│    5     create_app().run(debug=True, port=5000)                                 │
│                                                                                  │
│  The project's documented startup command invokes Flask's development server in  │
│  debug mode on port 5000.                                                        │
│                                                                                  │
│  Q  Someone launches `python run.py` on a host reachable by other machines, and  │
│     a request causes an unhandled exception. What response and server behavior   │
│     should you expect, and what deployment assumption must hold for this entry   │
│     point to be safe?                                                            │
│                                                                                  │
╰──────────────────────────────────────────────────────────────────────────  2/3  ─╯
  Type your answer, or  h hint · e explain · s skip · q quit
› It shows an error page.
  ◐ Partial    You’re right that an error page is involved, but this is too         
               surface-level: explain that `debug=True` exposes detailed traceback  
               information and an interactive debugger when the exception is        
               reached. Also address the key deployment assumption that this        
               development server must remain unreachable by untrusted machines     
               (and is not explicitly bound to localhost).                          
  Answer again, or  h hint · e explain · s skip · q quit
› h
  Hint         Consider what `debug=True` changes and whether the bind address is   
               explicitly controlled here.                                          
› debug=True turns on the Werkzeug debugger: an unhandled exception returns a full 
traceback page with an interactive Python console in the browser, guarded only by a 
PIN printed in the server log. And nothing binds it to localhost explicitly. So it's
only safe if the port is never reachable by untrusted machines — it's a 
local-development entry point, not something to deploy.
  ✓ Owned      You correctly describe the unhandled-exception response, the         
               interactive debugger/PIN risk, and the lack of an explicit           
               localhost bind. You also correctly identify the required local-only  
               deployment assumption; additionally, a PIN should not be treated as  
               sufficient isolation from untrusted clients.                         

╭─  architecture · splitter/app.py:18-22  ─────────────────────────────────────────╮
│                                                                                  │
│    18 def create_app(database=None):                                             │
│    19     app = Flask(__name__)                                                  │
│    20     app.config["DATABASE"] = database or os.environ.get("SPLITTER_DB", DE  │
│    21     init_db(app.config["DATABASE"])                                        │
│    22     app.teardown_appcontext(close_db)                                      │
│                                                                                  │
│  Application creation selects a filesystem database path and initializes the     │
│  fixed schema before serving requests.                                           │
│                                                                                  │
│  Q  Two application instances are started on different hosts with the same       │
│     source tree, and a client creates a group through one of them. Where does    │
│     that group's data go, and what must be true for the other instance to see    │
│     it after a restart or schema change?                                         │
│                                                                                  │
╰──────────────────────────────────────────────────────────────────────────  3/3  ─╯
  Type your answer, or  h hint · e explain · s skip · q quit
› It goes into a SQLite file on that host.
  ◐ Partial    You’re right that the data is written to a SQLite file on the host.  
               However, you need to explain whether the other host’s instance uses  
               the same file (and what shared filesystem/path would be required),   
               plus the implication that `CREATE TABLE IF NOT EXISTS` does not      
               perform schema migrations.                                           
  Answer again, or  h hint · e explain · s skip · q quit
› e
╭─  Explanation  ──────────────────────────────────────────────────────────────────╮
│  Each instance writes to its own configured SQLite file unless they              │
│  deliberately share a filesystem path. The default file is repository-relative,  │
│  and database files are ignored by Git. Restarting preserves data only if the    │
│  same file is retained; changing the schema is not supported by the CREATE IF    │
│  NOT EXISTS setup, so migrations would be needed for existing databases.         │
│                                                                                  │
│  Alternatives                                                                    │
│    • Use a client/server database such as PostgreSQL.                            │
│    • Use a managed database with migrations and connection pooling.              │
│    • Keep SQLite but use an explicit migration framework and a deployment-owned  │
│  database path.                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────╯

╭─  Session complete  ─────────────────────────────────────────────────────────────╮
│                                                                                  │
│  2 owned   1 partial   0 to revisit                                              │
│                                                                                  │
│  Repo ownership  ━━━━                      0% → 18%  (2/11 decisions)            │
│                                                                                  │
│  Next  mentor review --more  (8 decisions left)                                  │
│  Retry  mentor review --revisit  (1 not owned yet)                               │
│  Record  .mentor/DECISIONS.md                                                    │
│                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────╯
```
