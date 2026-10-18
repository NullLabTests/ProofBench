# Upstream research note: perplexityai/SPACE

Research date: 2026-10-18. Method: `gh repo view perplexityai/SPACE` succeeded; full shallow clone obtained via
`git clone --depth 1 https://github.com/perplexityai/SPACE /tmp/opencode/upstream/SPACE`.
Local checkout commit: `80840e883982cf4a47abefbae2ce90ddd6a2c2cc` ("[space] drain live data-plane streams on SIGTERM
instead of cancelling them at once (#27)", 2026-10-17). All file paths below are relative to that checkout unless a
URL is given. This is a real, substantial repository (~25 MB, Rust workspace version `0.8.0` per `Cargo.toml`),
**not** a README-only placeholder. Repo metadata: created 2026-10-01, default branch `main`, primary language Rust,
license Apache-2.0, last push 2026-10-18. Hosted docs: https://space.docs.perplexity.ai/guide/index.html and
https://space.docs.perplexity.ai/api/index.html (not fetched; source docs in the clone were used instead).

## 1. What the project actually implements

SPACE (README.md, line 7): "SPACE (Sandboxed Platform for Agentic Code Execution) is a sandbox platform for running
code in isolated Firecracker microVMs. Applications use its HTTP API to create Linux environments, execute commands,
collect output, and manage sandbox lifecycles."

Core concepts (`docs/architecture.md`): **Template** (starting filesystem + runtime config), **Sandbox** (isolated
microVM with own writable filesystem), **Process**, **Command session** (connection info + auth for one command;
attaching starts the process), **Operation** (record of an async create/pause/suspend/wake/delete).

Management plane / execution plane / output collection are cleanly separated:

- **Management plane** (HTTP + bearer token): "The API records desired state in PostgreSQL. Controllers and worker
  services reconcile the running system with that state, so an accepted request is not a readiness signal."
  (`docs/architecture.md`). Desired state flows: API → PostgreSQL → cluster controller → Kubernetes sandbox pod →
  SPACE runtime shim (Go, `shim/`) → worker services → Firecracker microVM → guest process.
- **Output / data plane** (separate endpoint + session-scoped token): command output uses "a separate data-plane
  connection and a session-scoped attachment token" (README.md). "Management and attachment tokens are not
  interchangeable" (`docs/architecture.md`, §Security boundaries). The data plane streams SSE (or WebSocket attach)
  directly between the application and the guest process, bypassing the control plane.
- **Sandbox technology**: Firecracker microVMs (one VM per sandbox). Not containers for the execution boundary.
  A compiled catalog pins Firecracker releases/kernels (`docs/runtime-manager-catalog.md`): default "E0" binding is
  Firecracker 1.15.1 / Linux 6.1.155, snapshot format 9.0.0; also approved bindings for Firecracker 1.16.x and
  1.17.0. Root filesystems use "btrfs copy-on-write" (`docs/architecture.md`, service responsibilities table).
- **Pluggable execution environments**: `docs/execution-environments.md` defines a content-addressed
  "execution environment" identity (SHA-256 over runtime + kernel + isolation + boot profile):
  "An execution environment binds a runtime, its host requirements, a guest platform, boot inputs, isolation
  semantics, and an adapter compatibility profile. Its reference is the SHA-256 of that complete definition."
  Only Firecracker/KVM ("hardware VM boundary") is implemented today; the schema is explicitly extensible
  ("A host facility must get a distinct provider when its adapter is implemented").
- **Executor-substrate abstraction (control plane)**: SPACE can "manage workers directly or through Kubernetes"
  (`docs/architecture.md`). `crates/libs/api/src/controllers/substrate/direct.rs` (direct adapter, no k8s pods) vs
  `crates/libs/api/src/controllers/substrate/kubernetes/` (used by the local Kind install). `ARCHITECTURE.toml`
  mechanically fences Kubernetes access to the substrate module via a pattern ratchet on `as_kubernetes()`.
- **Async lifecycle**: every lifecycle mutation returns an `operation_id`; clients poll until `succeeded`.
  "Sandbox lifecycle changes are asynchronous: the API returns an operation ID that you poll for completion."
- **Internal gRPC**: rich inter-service protobuf surface under `proto/` — e.g. `WorkerApi` in
  `proto/node/api/v1/worker.proto` (`CreateSandbox`, `StartSandbox`, `PauseSandbox`, `SuspendSandbox`, `WakeSandbox`,
  `SandboxStats`, `SpacedStartProcess`, …), `ClusterApi`, `BuilderApi`, `TemplateManager`
  (`proto/template/manager/v1/manager.proto`), sandbox-manager (`proto/sandbox/manager/v1/manager.proto`), guest-side
  `Process`/`Filesystem`/`Meta` services (`proto/spaced/host/v1/host.proto`, `proto/spaced/bridge/guest/v1/guest.proto`).
- **Other planes**: builders build templates separately from user sandboxes; object storage (Versity S3 gateway in
  Kind) holds templates/snapshots; a net gateway does egress policy + TLS interception with per-sandbox
  `NetworkPolicyV1`; credential-manager injects credentials; warm pools and base snapshots skip cold boot; an
  operator CLI (`crates/apps/admin/cli`), a web UI, and an **E2B Compatibility Wrapper (ECW)** that translates the
  E2B API at the edge (`docs/ecw.md`).
- Services run as Kubernetes DaemonSets per node (node-manager, sandbox-manager, template-manager, volume-manager,
  credential-manager, runtime-manager…), per `docs/installation.md`: "Each node service … runs as its own DaemonSet,
  as in production".

## 2. Documented assumptions, prerequisites, deployment requirements, limitations

From `docs/installation.md` (the local Kind guide) and `docs/architecture.md`:

- **Host**: "Use an apt-based **Linux x86_64 host with KVM**. The host needs `/dev/kvm`, `/dev/net/tun`, loop devices,
  btrfs support, and a local Docker daemon that permits privileged containers. A VM must expose the required devices
  and support nested virtualization; these instructions do not run directly on macOS." Tools: Bash, Git, curl, tar,
  OpenSSL, Python ≥3.8, ssh-keygen, Docker; the prereq installer adds Kind, kubectl, Helm, grpcurl, Tilt, Go, jq;
  root/sudo needed. First build "compiles the Rust workspace and builds the seed template".
- **Deployment shapes**: documented local deployment is a **Kind (Kubernetes-in-Docker) cluster**; a reference EKS
  deployment exists at `infra/space/aws/reference/` ("applied on a schedule"). `docs/architecture.md` says "The direct
  adapter … calls worker services without creating Kubernetes sandbox pods", i.e. a non-k8s mode exists, but
  `docs/installation.md` states: "This guide covers the Kubernetes-based local setup, not a Kubernetes-free
  deployment."
- **Privileges**: "Firecracker isolates guest execution. Host-side services still require privileges to manage VMs,
  storage, and networking." Sandbox pods run in a separate `sandboxes` namespace with restrictive NetworkPolicies.
- **Resource topology**: ~a dozen per-node DaemonSets + control plane (API, PostgreSQL, cluster controller, data
  plane, builders, object storage, UI). Development passwords only ("This deployment uses development passwords and
  signing keys. Keep it private").
- **Stability/limitations** (`docs/versioning.md`): "SPACE 0.8.0 establishes the public release baseline";
  0.9.0 is the "final planned breaking-change release"; 1.0.0 will be stable. Guests supported in 0.8:
  "`spaced` guest versions **>=0.1.0 and <0.9.0**". Contract stability at 1.0 covers exactly three surfaces: "The
  native HTTP API. The worker `node-api` gRPC/protobuf API for custom cluster management. The `spaced-bridge`
  gRPC/protobuf API for custom in-guest integrations." Rust crate APIs are explicitly outside the guarantee.
- **Data durability limits** (`docs/architecture.md`): file writes are "persisted at lifecycle boundaries, not per
  write: an acknowledged one is not guaranteed to survive a sandbox crash, forced stop or host failure." Command
  streams are live, "with no replay"; `Last-Event-ID` reconnect yields `resync_required`, not replay.
- **Idle policy**: "By default, sandboxes created through the SPACE API suspend after six hours without access or
  command activity. This is an idle limit, not a maximum lifetime."
- No GitHub Releases exist (`gh release list` returned empty); Bundle CI "tags images by commit".
- No macOS/Windows execution; production qualification covers only Linux/x86_64 E0
  (`docs/execution-environments.md`: "Production qualification covers only Linux/x86_64 E0").

## 3. Design principles that transfer to ProofBench

- **Separation of management plane vs data plane vs output collection.** Control requests (create/delete/poll) go
  one way with one credential; byte streams go over a separate endpoint with a *session-scoped, single-purpose*
  token. For ProofBench: keep "prove/run a task" (management) separate from "collect the big transcript/artifacts"
  (data path), and never reuse the admin token on the data path.
- **Explicit three-state distinction.** SPACE rigorously separates: sandbox lifecycle state (`running`, `paused`,
  `suspended`…), operation progress state (`queued/running/succeeded/failed/canceled/expired`), and command exit
  status. Quotes: "An operation's `state` describes the lifecycle request; the sandbox's `state` describes the
  environment. Neither is the exit status of a command." ProofBench should model at least: run/job state, executor
  (VM/container/process) state, and command exit — as distinct fields with distinct polling endpoints.
- **Async operations with pollable IDs + idempotency keys.** Mutations return `operation_id` (202 semantics);
  `Idempotency-Key` required on lifecycle mutations, kept 24 h; the error envelope carries an authoritative
  `retryable` flag and clients are told to follow it, not HTTP status. A write-ahead "state.json before the network
  call" pattern (`examples/first_sandbox.py`) makes ambiguous outcomes recoverable. All highly reusable for
  ProofBench runs that must never be silently duplicated.
- **Explicit trust boundaries.** Firecracker is the isolation boundary; k8s/privileged host services are trusted;
  guest network egress is per-sandbox policy with optional TLS interception; management vs attachment tokens are
  type-separated; template provenance can be allowlisted (`SPACE_TRUSTED_TEMPLATE_STORAGE_BUCKETS`). For ProofBench:
  name the trusted computing base explicitly (hypothesis-rewriting code from evaluated code), give each a typed
  credential, and encode egress/resource policy per execution class.
- **Resource limits as first-class requested shape, honestly reported.** `resources.vcpu/memory_mib/disk_mib`;
  response semantics: "Omitted fields remain `null` in the response while the deployment applies its defaults; the
  response does not reveal the resolved shape", and "Stored resource requests, not a measurement of resolved guest
  capacity. Null fields mean no explicit value was recorded, not zero capacity." Live stats endpoint
  (`getSandboxStats`: cpu, memory, pids, network counters) is separate from requested shape. ProofBench should copy
  the requested-vs-observed distinction.
- **Pluggable executor backends behind a content-addressed environment identity.** The `Substrate` adapter
  (direct vs Kubernetes) + `SubstrateCapabilities` (instead of scattered `if k8s` checks) + the execution-environment
  descriptor (runtime+kernel+isolation hashed into a reference; "Installation does not select an environment")
  is a strong template for ProofBench's "pluggable executor backends": a small trait/interface, capability
  advertisement, and policy separate from availability.
- **Reconciliation, not request execution.** Desired state in a durable store; controllers reconcile; readiness is
  polled. Plus warm pools / base snapshots to skip cold boot where latency matters.
- **Extensible response enums.** Request-side enums are closed; response-side vocabularies are open strings with
  documented examples ("Clients must accept values not listed in examples"), so servers can evolve. Cheap and worth
  copying for ProofBench's result schema.
- **Architecture enforcement in CI** (`ARCHITECTURE.toml`): pattern ratchets that fence Kubernetes access to one
  module, cap file sizes, ban catch-all crate names. Inexpensive, high-leverage; adaptable to ProofBench.
- **Idle limits ≠ max lifetime; persistence at lifecycle boundaries documented honestly.** Both directly relevant to
  long proof runs on a small machine.

## 4. Components impractical or inappropriate to reuse on a CPU-only, 14 GiB-RAM, local-first platform

- **The whole Firecracker/KVM microVM stack** (firecracker binaries, guest kernels, jailer, snapshot formats,
  btrfs CoW rootfs plumbing, netns/nftables containment): requires KVM (`/dev/kvm`, nested virt), root, btrfs,
  and per-VM memory overhead that does not fit 14 GiB for many concurrent sandboxes. For ProofBench's scale, a
  container- or namespace-based executor (or even plain subprocess with cgroups) is the realistic backend; SPACE's
  *interfaces* transfer, its VM machinery does not.
- **The Kubernetes deployment machinery**: Kind cluster, per-node DaemonSets (~10 services), NetworkPolicies,
  Tiltfile dev loop, EKS reference. A local-first single-host platform should use the **direct adapter pattern**
  (SPACE itself shows the control plane can run without k8s), not the k8s adapter.
- **PostgreSQL control plane + object storage (versitygw) + S3 artifact stores**: heavyweight for local-first;
  SQLite/a file-backed store matches ProofBench's footprint. (Conversely, SPACE's own SQLite usage in
  runtime-manager shows they too use lighter stores at the node layer.)
- **The full inter-service gRPC mesh** (cluster-api, node-api, worker-api, credential broker, net gateway,
  template/volume/build managers, TLS-rotation runbooks): dozens of services exist to run a multi-node fleet.
  ProofBench needs one binary (or a small pair: manager + runner) with the same *conceptual* boundaries.
- **Telemetry stack** (DogStatsD/Datadog + OTLP selectors, Go runtime metrics) and the ECW E2B-compat edge:
  irrelevant locally; the observability *contract* idea (a sink selector, fail-fast config validation) transfers,
  the backends don't.
- **Warm pools / cross-node placement / quarantine recovery / artifact backup**: fleet-scale features whose
  complexity (see `docs/native-api-hardening.md` referenced from README) outweighs local value.
- Note the licensing angle below: reuse is legally safe (Apache-2.0) but the codebase is a fleet platform, so
  **extracting ideas + writing a small native implementation** is more appropriate than vendoring crates.

## 5. License and attribution obligations

- **License file exists**: `LICENSE` at the repository root (11,371 bytes).
  SHA-256: `18a6a5deee27a2c6f1271ea4910830cb6653b0efc58aa31da138670ebb27cfa7`.
  It is the **verbatim standard Apache License, Version 2.0, January 2004** text ("TERMS AND CONDITIONS FOR USE,
  REPRODUCTION, AND DISTRIBUTION" … "APPENDIX: How to apply the Apache License to your work."), with a single
  project-specific first line:

  ```
  Copyright 2026 Perplexity AI

                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/
  ```

  and the standard appendix boilerplate ending ("Copyright [yyyy] [name of copyright owner] … limitations under the
  License."). `gh` confirms `licenseInfo: {"key": "apache-2.0", "name": "Apache License 2.0"}`. README.md §License:
  "SPACE is licensed under the [Apache License, Version 2.0](LICENSE)."
- **No NOTICE file exists** (checked with `find . -iname 'NOTICE*' -not -path './.git/*'` — no results), so there is
  no NOTICE-attribution obligation on redistributors beyond the Apache-2.0 section 4 requirements.
- **Obligations if you copy the code**: keep the Apache license text + the "Copyright 2026 Perplexity AI" notice and
  any NOTICE contents (none) in redistributions; state changes to copied files; no copyleft, no share-alike, no
  network-use clause (it is *not* AGPL). Patents are granted (Apache-2.0 §3) with the standard patent-termination
  clause — relevant and favorable if SPACE-adjacent patents were ever asserted (defensive termination only).
- **Reimplementing ideas without copying code**: safe. Apache-2.0 imposes no obligation on independently written
  code that merely implements documented API shapes or general concepts. For an optional ProofBench adapter written
  *against* the SPACE HTTP API (client-side, no copied code), there is effectively no licensing obligation; still
  advisable to credit the project. If any SPACE source is vendored or adapted (even lightly), include the license
  header/copyright and mark modifications per sections 4(b)/4(d). No copyleft contamination applies to separate
  programs that link only to Apache-2.0 code.

## 6. The actual public API (enough detail to write an optional adapter)

Two public surfaces: the **native SPACE HTTP API** (control plane, bearer token, JSON, served at `/v1`; "shared-host
deployments may use `/api/v1` instead") and the **data plane** (SSE/WebSocket, session token). The API serves its
generated OpenAPI document at **`/openapi-m1.json`** ("with request fields, response schemas, and errors";
`docs/api/index.md`). The authoritative operation manifest is
`crates/libs/public/api/src/routes.rs`; request/response types are in `crates/libs/public/api/src/lib.rs`.
`docs/api/index.md`: "This reference covers 14 supported HTTP operations" — M1-supported ones are marked below;
`incubating` operations are outside the supported contract.

### 6.1 Control-plane operations (management token: `Authorization: Bearer <token>`)

From `NATIVE_V1_OPERATIONS` in `crates/libs/public/api/src/routes.rs` (method, path, operationId, status):

M1-supported:
- `GET /v1/sandboxes` — listSandboxes → `PublicPage<PublicSandbox>` (`data`, `next_cursor`)
- `POST /v1/sandboxes` — createSandbox → `SandboxOperationResponse {operation_id, sandbox_id}`
- `GET /v1/sandboxes/{sandbox_id}` — getSandbox → `PublicSandbox`
- `DELETE /v1/sandboxes/{sandbox_id}` — deleteSandbox → `SandboxOperationResponse`
- `POST /v1/sandboxes/{sandbox_id}:pause` | `:suspend` | `:wake` — pauseSandbox / suspendSandbox / wakeSandbox →
  `SandboxOperationResponse` (all require `Idempotency-Key`)
- `GET /v1/operations/{operation_id}` — getOperation → `PublicOperationRecord`
- `POST /v1/sandboxes/{sandbox_id}/commands` — createCommand → `PublicCommand`
- `GET /v1/sandboxes/{sandbox_id}/processes` — listProcesses; `GET …/processes/{process_id}` — getProcess →
  `PublicProcess`; `POST …/processes/{process_id}:kill` / `:signal` — killProcess / signalProcess →
  `ProcessMutationResponse {ok}` (signal body: `ProcessSignalRequest {signal: 1..64}`)

Incubating (shape-stable enough for an experimental adapter, but not contractually supported):
- PATCH `…/{id}` updateSandbox (`UpdateSandboxRequest {metadata, resources, network_policy, auto_lifecycle}`)
- `POST …/{id}:start|stop|kill|restore|resume|checkpoint|rollback|enable_snapshots|disable_snapshots|set_timeout`
- File ops: `POST /v1/sandboxes/{id}/files:list|mkdir|read|write|write_batch|remove|rename|stat|modified|changes_enable|changes_disable`
- Sessions: `POST …/process-sessions`, `…/terminal-sessions`, `…/file-watch-sessions`, `…/port-sessions`,
  `…/protocol-sessions`; `GET/DELETE …/sessions[/{session_id}]`
- Ports: `GET …/ports`, `POST …/ports/{port}/open|close`; snapshots: `GET …/snapshots[/{snapshot_id}]`
- `GET …/stats` (getSandboxStats), `GET …/metrics-stream`, `GET …/lifecycle-events`, `GET …/network-policy`
- `GET /v1/operations/{id}/events` (listOperationEvents); credential-references CRUD; `GET /v1/templates[/{name}]`
- Auth (not in the manifest but used by the guide): `POST /auth/v1/sessions` with
  `{email, password}` → `{token}` (`docs/installation.md` §Authenticate).

### 6.2 Key request/response fields (from `crates/libs/public/api/src/lib.rs`)

- `CreateSandboxRequest`: `template` (e.g. `seed:latest` or digest ref), `runtime` (`"fc"` = Firecracker),
  `name`, `env` (map), `metadata` (string/number/bool values), `resources {vcpu?, memory_mib?, disk_mib?}`,
  `network_policy?` (`NetworkPolicyV1`), `auto_lifecycle?`, `idle_timeout?` (e.g. `600s`),
  `idle_action?` (`"delete"|"suspend"`).
- `PublicSandbox`: `id` (`sbx_<uuid7>`), `name`, `state` (extensible: `creating|stopped|starting|running|pausing|
  paused|resuming|suspending|suspended|restoring|migrating|stopping|failed|deleting|deleted`), `failure_code`,
  `conditions[] {condition_type ("ready"|"network_ready"), status, reason, message}`, `template`, `template_digest`,
  `resources`, `metadata`, `expires_at`, `idle_timeout`, `idle_action`, `created_at`, `updated_at`.
- `CreateCommandRequest`: `command` (argument **array**, not shell string), `cwd?`, `env`, `pty? {cols,rows}`,
  `stdin?` (bool), `user?`, `timeout?` (`"30s"`, `"5m"`, `"1h"`).
- `PublicCommand` (response): `session_id` (`proc_…`), `process_id` (opaque, not the guest PID), `sandbox_id`,
  `state` (`pending|attaching|open|reconnecting|closing|closed|revoked|failed`), `attach` → `DataPlaneAttachInfo
  {url, events_url?, token, expires_at, token_transport[]}`, `created_at/updated_at/expires_at`.
- `PublicOperationRecord`: `id` (`op_…`), `kind` (18 kinds: `create_sandbox`, `suspend_sandbox`, `fork_sandbox`…),
  `state` (`queued|running|succeeded|failed|canceled|expired`), `target_type`, `target_id`, `progress_message`,
  `terminal_error_code?`, `terminal_error?`, `result?` (tagged union `sandbox|template|session|fork`),
  timestamps.
- `PublicProcess`: `process_id`, `pid`, `command[]`, `cwd`, `user`, `tag`.
- `SandboxStatsResponse`: `sandbox_id, cpu_max, memory_max, memory_current, pids_max, pids_current, cpu_usage_usec,
  network_tx_bytes, network_rx_bytes, net_gateway_reachable, tcp_active/total/denied_connections,
  udp_active_mappings, bytes_forwarded`.
- Errors: `PublicErrorEnvelope {code, message, request_id, retryable, details[{key,value}]}` with codes
  `invalid_request|unauthorized|forbidden|not_found|conflict|failed_precondition|capacity_unavailable|rate_limited|
  idempotency_conflict|operation_failed|service_unavailable|internal`. Data-plane HTTP errors:
  `DataPlaneHttpErrorEnvelope {error {code, message, retryable}}`.
- Pagination: `PublicPage<T> {data, next_cursor}`; cursors are opaque, ≤4096 bytes, per-collection.
- Idempotency: `Idempotency-Key` header; 24 h retention on lifecycle ops and command creation; file writes dedupe
  only ~60 s in-memory (`docs/api/index.md`).

### 6.3 Data plane (SSE)

`GET /v1/sessions/{session_id}/events` on the **data-plane origin** with the **session attachment token**
(`streamSessionEvents`, M1-supported). Server-sent events, JSON frames per `DataPlaneServerFrame`
(`crates/libs/public/api/src/lib.rs`):
- `{"type":"attached","session_id","route_generation","current_node_id"}`
- `{"type":"process_started","process_id","pid"}`
- `{"type":"stdout","seq","data_base64"}` / `{"type":"stderr",…}`
- `{"type":"process_exited","process_id","exit_code","status"}` where status ∈
  `exited|signaled|timed_out|unknown` — success = `process_exited` with `exit_code == 0` and no prior `error` /
  `resync_required` frame (`examples/first_sandbox.py` enforces exactly this)
- `{"type":"error","code","message","retryable"}`, `{"type":"resync_required","reason"}`,
  `{"type":"closed","reason"}`, `{"type":"backend_reconnecting"/"backend_reconnected",…}`, `{"type":"file_event",…}`.
Client frames (WebSocket attach / `attachSession`): `attach {token}`, `input {seq,data_base64}`, `resize {cols,rows}`,
`signal {seq,signal}`, `close_stdin {seq}`, `heartbeat {seq}`, `close`.
Also: `GET /v1/sessions/{session_id}/proxy/{*path}` — transparent proxy to a sandbox-local service (incubating).

### 6.4 Internal gRPC (for reference; node-api is a 1.0-stability contract for "custom cluster management")

`proto/node/api/v1/worker.proto` `WorkerApi` ≈ per-node worker: `CreateSandbox`, `StartSandbox`, `StopSandbox`,
`KillSandbox`, `DeleteSandbox`, `SandboxState`, `GetSandboxHealth`, `ListSandboxes`, `PauseSandbox`, `ResumeSandbox`,
`WakeSandbox`, `CreateSandboxSnapshot`, `SuspendSandbox`, `SandboxStats`, `UpdateSandbox`, `SetSandboxAutoLifecyclePolicy`,
`SetSandboxNetworkPolicy`, all `Spaced*` guest passthroughs (e.g. `SpacedStartProcess` → stream `ProcessEvent`),
`ExposePort`/`UnexposePort`/`AllowPort`/`DenyPort`. `ClusterApi` (template releases, data-plane session routing,
reconcile refs, quarantine plans) and `BuilderApi` live in the same directory; guest bridge services in
`proto/spaced/bridge/guest/v1/guest.proto`. Message-level fields for these are in the corresponding `.proto` files
in the clone; the reader interested in an adapter should target the **HTTP surface** above, which is the documented
client contract.

## 7. Uncertainties requiring further verification

- **The hosted docs and live OpenAPI document were not fetched.** The claim that `/openapi-m1.json` contains the full
  field-level schemas comes from `README.md` and `docs/api/index.md`; the schema is generated at build time from the
  Rust types (`crates/libs/public/api`, schemars). To write a production adapter, generate/fetch `/openapi-m1.json`
  from a running deployment (or run `bash scripts/build-api-docs.sh`, which needs Node 22.12+, npm 10+, the Rust
  toolchain, a C compiler and `protoc`) and diff it against §6.
- **The K8s-free ("direct substrate") deployment is real in code but not documented as an installable path.**
  `docs/architecture.md` describes the direct adapter; `docs/installation.md` says it does "not" cover a
  Kubernetes-free deployment. Whether a single-host direct-mode deployment is practical today is unverified.
- **"14 supported HTTP operations" vs the manifest.** `docs/api/index.md` says 14; I counted the M1-supported entries
  in `routes.rs` (13 control-plane + 1 data-plane = 14) — consistent, but the exact membership list is my inference
  from the `M1Supported` markers, not an explicit list in the docs.
- **No GitHub Releases and no tags visible in the shallow clone** (`gh release list` empty; `git tag` empty — a
  depth-1 clone may omit tags, but the release list supports "no releases"). The `0.8.0` version is the Cargo
  workspace version and the docs' "public baseline"; there is no tagged 0.8.0 release artifact to pin.
- **Exact license-file bytes beyond the hash**: I verified the head (copyright line), the presence of the APPENDIX,
  the ending boilerplate, length 11,371 bytes and SHA-256 above; I did not byte-diff it against
  apache.org's canonical text. The hash + spot checks make "verbatim Apache-2.0" near-certain, not formally proven.
- **Not audited**: actual security properties of the Firecracker configuration, the strength of the token minting,
  and the network gateway. This note reports documented boundaries, not verified ones.
- **ECW tested-compatibility surface** (`docs/ecw.md`): tested only against `e2b==2.21.1` /
  `e2b-code-interpreter==2.6.2`; "Other releases and the JavaScript SDK may work … but they are not currently covered
  by the repository's compatibility tests." I only skimmed the first 80 lines; the limitation section beyond that
  was not read.
- **Repository is very young** (created 2026-10-01, ~2.5 weeks old at research time, 27 merged PRs). Expect rapid
  change; any adapter should pin a commit (this note: `80840e883982cf4a47abefbae2ce90ddd6a2c2cc`).
