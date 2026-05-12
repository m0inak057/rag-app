# Planning Docs — Read Me First

This folder is your control room for the v2 upgrade. Five files. Read in this order, then refer back as needed.

| # | File | Purpose | When to look at it |
|---|------|---------|--------------------|
| 1 | `PRD.md` | What we're building, why, and what counts as done. | Once at the start. Re-read before each phase. |
| 2 | `ARCHITECTURE.md` | How the v2 system is structured. Component-by-component changes. | When you start coding any new component. |
| 3 | `PHASES.md` | The day-by-day plan, ordered, with explicit done-gates. | At the start of every working session. |
| 4 | `RULES.md` | Hard rules that prevent the common failure modes. | When you're tempted to do something clever. |
| 5 | `COMPLETION.md` | Live state — what's done, what's next, what's blocked. | Start and end of every session. |

---

## How to use this stack

**Day 1.** Read PRD top to bottom. Read ARCHITECTURE top to bottom. Skim PHASES. Skim RULES.

**Every working session.** Open COMPLETION first. Look at the "Next 3 things" block at the bottom. Pick one. Do it. Update COMPLETION before you stop.

**When stuck.** Re-read the relevant section of ARCHITECTURE and the relevant rule(s) in RULES.

**When done with a phase.** Verify the "done when" gate in PHASES. Update COMPLETION. Commit.

---

## Quick reference

- Goal: multi-doc reasoning with citations, plus an evaluation harness with measured numbers.
- Branch: `v2-multidoc-eval`.
- Estimated time: ~15 working days realistic, ~22 with cushion.
- Critical insight: stopping after Phase 4 still gives you a meaningfully better project. Phases 5–6 are what gives you a *measurable* better project.
- Two non-negotiables: (1) citations are validated in code, (2) test set is frozen once eval starts.

---

## If you only have time for one thing

Read **PRD §7 (Success criteria)** and **PHASES Phase 4 + Phase 6**. Those three sections together describe 80% of the value.
