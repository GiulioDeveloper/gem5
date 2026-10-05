## VP Design Plan

- First, I want to create a VP framework that can stay consistent irrespective of the underlying exact value prediction algorithm.
    - This means the VP's interaction with the pipeline will be via a unified API: (1) calling the VP for making the prediction at rename stage, (2) training the VP at writeback stage, and (3) squashing the pipeline in case of wrong prediction
    - For squashing, I think we can reuse most of the machinery from MRN study.
    - I am envisioning a base value predictor class which will have a pure virtual function predict() and train(). Each new VP alogrithm will derive from the base class and define it's own predict and train functions. Basic VP-level stats (e.g., total loads seen, total predictions, correct predictions, flush cost, etc.) can be maintained at the base class level. Each derived class will contain stats that gives us the exposure to their prediction/train algorithm.
        - This is my vision. Please feel free to change it based on how you see fit adhereing to golden standards of software engineering.
        - Study the `mem/prefetch` directory. This defines prefetcher infrastructure for gem5 with the same principle as I outlined above: the `base.hh/.cc` and `queued.hh/.cc` define the base prefetcher class, which then every other prefetcher extends to. I am envisioning the VP infra in the same way: a unified infra to interfact VP with the pipeline, and multiple VP implementations. You can also check the `mem/replacement_policies` directory. It's also designed in the same way.
        - Use the directroy of this design doc (`/home/rbera/work/garfield/gem5/src/cpu/o3/vp`) for VP infra.
    - Provide a user-specified knob to employ VP for only loads or to all instructions. Provide another knob to restrict VP to only scalar instructions (load or all), since vector instructions' value prediction needs more care (we have to predict every 64b splice of the value multiple times).

- Once the infra is done, let's fist start with a very basic VP similar to Lippasti's MICRO'96 paper: last value prediction. The key idea is to maintain a PC-indexed value prediction table (VPT). Each entry will have PC tag, the last value, and a N-bit confidence counter. The confidence counter starts from zero an increments every time the current value is same the last value. Once the counter crosses a threshold, we will use that value to break the data dependency. At writeback time, if the value does not match, we reduce the confidence. There can be two mode of reducing the confidence: (1) set confidence to zero, or (2) decrement the confidence. Keep this knobbed, and the default should be reset to zero.
    - The goal of this simple predictor to not acheive the highest benefit, but to test whether the entire infra is working or not.
    - Once we are confident with the VP infra, then we will move to two more sophisticated and state-of-the-art method of VP: (1) VTAGE and (2) EVES. Papers of both of these are inside `src/cpu/o3/vp/papers`. But that comes later.

- One critical aspect of adding VP in a system that already has MRN is the optimization priority ladder. The priority would be MRN -> VP -> normal execute. Write the code as such. But for testing purposes, we can simply test with MRN off for now. Later we will expand.

## Testing

We will take two-stage approach for testing: first VP for only loads, and then for all instructions. For each stage we will create a test microbenchmark in `/home/rbera/work/garfield/gem5-infra/workloads/microbenchmarks`. The VP should show high coverage (i.e., fraction of instructions that are correctly predicted by VP), high accuracy (i.e., fraction of total predictions that are correct), and performance gain over the baesline system without VP and MRN.

Once the microbenchmarks show that VP is working, then we move to run it with 190 SPEC26 checkpoints.

## Deliverable Stages

- Stage-I:   Create the VP infra
- Stage-II:  Last Value Predictor implementation
- Stage-III: Testing last value predictor with microbenchmarks
- Stage-IV:  Deploying last value predictor on SPEC26
