# November 18 recovery status
First production 44267659616 failed at 08:35 UTC in Install System Dependencies, exit 124, before Python dependencies, research or TTS. No production or voice-recovery artifacts exist. No completed take was lost.
Root cause: earlier mirror normalization covered azure.archive.ubuntu.com only. Actual download logs used us-east-2.ec2.archive.ubuntu.com and exceeded the bounded 240-second install limit.
Repair on main 2160a634816349e23f8de2361bfbd8e8a070170c extends normalization to regional EC2 mirrors, retains Ubuntu primary archive/signature checks and bounded timeouts. Four shell substitution tests passed for Azure, two EC2 regions and untouched security archive. Actual runner success remains pending.
No active production at restart guard; no dated master or RSS item. Exactly one recovery started: 44286438860, trigger 78ef69d. No forced rebuild. Do not start another while active.
November17 remains latest public episode, 21:54. November18 publication and Spotify arrival unverified. Earlier title/candidate and Marketing readiness record is in 2026-11-18-editorial-handoff.md. No native marketing actions or actual listening claimed.
