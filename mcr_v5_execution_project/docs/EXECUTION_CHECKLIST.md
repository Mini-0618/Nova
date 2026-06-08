# MCR v5.0 Execution Checklist

## Phase 0: Safety
- [ ] Local test only
- [ ] No external network
- [ ] No dangerous shell commands
- [ ] No user file deletion
- [ ] All logs to runtime_logs/

## Phase 1: Generate
- [ ] Run python make_mcr_v5_execution_project.py
- [ ] Enter mcr_v5_execution_project/
- [ ] Confirm src/mcr_v5/unified_loop.py exists

## Phase 2: Run
- [ ] python run.py
- [ ] See status: ok
- [ ] See steps: 15
- [ ] See events >= 15

## Phase 3: Health Check
- [ ] python src/mcr_v5/health_check.py
- [ ] Output: health_check: PASS

## Phase 4: Tests
- [ ] python -m pytest
- [ ] test_unified_loop_runs_15_steps passes

## Phase 5: 15-Step Verification
- [ ] Step 01: Environment Scan
- [ ] Step 02: World Model
- [ ] Step 03: Opportunity Detection
- [ ] Step 04: Goal Generation
- [ ] Step 05: Task Execution
- [ ] Step 06: Provenance
- [ ] Step 07: Failure Analysis
- [ ] Step 08: Pattern Detection
- [ ] Step 09: Immune Patrol
- [ ] Step 10: Self Repair
- [ ] Step 11: Cognitive Reflection
- [ ] Step 12: Global Broadcast
- [ ] Step 13: Homeostasis
- [ ] Step 14: Skill Evolution
- [ ] Step 15: Sleep Consolidation

## Phase 6: Output Check
- [ ] runtime_logs/provenance.jsonl generated
- [ ] runtime_logs/skills.jsonl generated
- [ ] runtime_logs/sleep_memory.jsonl generated

## Phase 7: Next Steps
- [ ] Connect TaskEngine to real tasks
- [ ] Connect FailureAnalyzer to real eval
- [ ] Connect EvolutionEngine to prompt evolution
- [ ] Connect Homeostasis to token/CPU/memory monitoring
- [ ] Connect SleepConsolidator to long-term memory
