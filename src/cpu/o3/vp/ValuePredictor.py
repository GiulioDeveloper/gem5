from m5.params import *
from m5.SimObject import SimObject


class BaseValuePredictor(SimObject):
    type = "BaseValuePredictor"
    abstract = True
    cxx_class = "gem5::o3::BaseValuePredictor"
    cxx_header = "cpu/o3/vp/base.hh"

    onlyLoads = Param.Bool(
        True,
        "Predict loads only; when false, every eligible (single scalar "
        "integer destination) instruction is in scope.",
    )
    scalarOnly = Param.Bool(
        True,
        "Restrict prediction to scalar destinations. Currently subsumed "
        "by the integer-only eligibility rule; the knob exists so the "
        "interface is stable when FP/vector support lands.",
    )
    historyPathBits = Param.Unsigned(
        16,
        "Width in bits of the VP-private path-history register "
        "maintained by the framework's history subsystem. Only "
        "consumed by history-aware predictors (VTAGE-class); LVP "
        "ignores it.",
    )


class LastValueVP(BaseValuePredictor):
    type = "LastValueVP"
    cxx_class = "gem5::o3::LastValueVP"
    cxx_header = "cpu/o3/vp/last_value.hh"

    entries = Param.Unsigned(4096, "Value prediction table entries")
    assoc = Param.Unsigned(4, "Value prediction table associativity")
    confBits = Param.Unsigned(4, "Confidence counter width in bits")
    confThreshold = Param.Unsigned(
        15,
        "Minimum confidence required to predict (minimum 1; 0 would "
        "predict on every table hit and is rejected)",
    )
    confDecrementOnWrong = Param.Bool(
        False,
        "Decrement (rather than reset to zero) confidence on a value "
        "mismatch, clamped below the confidence threshold",
    )


class VtageVP(BaseValuePredictor):
    type = "VtageVP"
    cxx_class = "gem5::o3::VtageVP"
    cxx_header = "cpu/o3/vp/vtage.hh"

    baseEntries = Param.Unsigned(
        8192, "VT0 (tagless, PC-indexed base component) entries"
    )
    taggedEntries = Param.Unsigned(
        1024,
        "Entries per tagged component (VT1..VTnumTagged); all tagged "
        "components share this size",
    )
    numTagged = Param.Unsigned(
        6,
        "Number of tagged components (VT1..VTnumTagged). The biased-"
        "rank token field packs 0 = none, 1 = VT0, 2..(1+numTagged) = "
        "VT1..VTnumTagged, so this must be <= 7",
    )
    historyLengths = VectorParam.Unsigned(
        [2, 4, 8, 16, 32, 64],
        "Per-tagged-component history length L(i), shortest to "
        "longest; size must equal numTagged, each length in [1, 128] "
        "(the history snapshot is 128 bits)",
    )
    baseTagBits = Param.Unsigned(
        12,
        "Tagged component 1's tag width; component i's (1-based) tag "
        "width is baseTagBits + i",
    )
    confBits = Param.Unsigned(
        3, "Saturating confidence-counter width, every component"
    )
    confThreshold = Param.Unsigned(
        7,
        "Minimum confidence required to predict (minimum 1; 0 would "
        "make the verify-site corrective reset unable to leave an "
        "entry below threshold -- squash-livelock hazard -- and is "
        "rejected)",
    )
    fpcVector = VectorParam.Float(
        [1, 1.0 / 16, 1.0 / 16, 1.0 / 16, 1.0 / 16, 1.0 / 32, 1.0 / 32],
        "Forward Probabilistic Counters: v[i] is the probability that "
        "the i -> i+1 confidence transition fires on a correct "
        "update; size must equal one per forward transition (2^"
        "confBits - 1). The reset to 0 on a wrong update is never "
        "probabilistic",
    )


class EVtageVP(BaseValuePredictor):
    type = "EVtageVP"
    cxx_class = "gem5::o3::EVtageVP"
    cxx_header = "cpu/o3/vp/evtage.hh"

    baseEntries = Param.Unsigned(
        8192,
        "VT0 (tagged, 2-way skewed base component) TOTAL entries "
        "across both ways; must be even, and half must be a power "
        "of two",
    )
    taggedEntries = Param.Unsigned(
        1024,
        "Entries per tagged component (VT1..VTnumTagged); all tagged "
        "components share this size",
    )
    numTagged = Param.Unsigned(
        6,
        "Number of tagged components (VT1..VTnumTagged). The biased-"
        "rank token field packs 0 = none, 1 = VT0, 2..(1+numTagged) = "
        "VT1..VTnumTagged, so this must be <= 7",
    )
    historyLengths = VectorParam.Unsigned(
        [2, 4, 8, 16, 32, 64],
        "Per-tagged-component history length L(i), shortest to "
        "longest; size must equal numTagged, each length in [1, 128] "
        "(the history snapshot is 128 bits)",
    )
    baseTagBits = Param.Unsigned(
        12,
        "VT0's tag width; tagged component i's (1-based) tag width "
        "is baseTagBits + i",
    )
    confBits = Param.Unsigned(
        3, "Saturating confidence-counter width, every component"
    )
    confThreshold = Param.Unsigned(
        7,
        "Minimum confidence required to predict (minimum 1; 0 would "
        "make the verify-site corrective punish unable to leave an "
        "entry below threshold -- squash-livelock hazard -- and is "
        "rejected)",
    )
    uBits = Param.Unsigned(
        2, "Saturating usefulness-counter width, every component"
    )
    tickMax = Param.Unsigned(
        1024,
        "TICK aging-pass threshold (accumulates NA - 5*ALL after "
        "every allocation attempt; at this value every entry's "
        "nonzero usefulness counter is decremented and TICK resets)",
    )
    burstGuardWindow = Param.Unsigned(
        0,
        "Burst-misprediction guard: while fewer than this many "
        "instructions have been renamed since the last delivered "
        "E-VTAGE misprediction, prediction emission is suppressed "
        "(the lookup and commit training still happen). 0 = off "
        "(default, the ratified fork); 128 = CVP-1 EVES's own "
        "behavior.",
    )


class EvesVP(BaseValuePredictor):
    """The composed EVES predictor: E-VTAGE + E-Stride (design doc
    docs/legacy-log/superpowers/specs/2026-08-14-estride-design.md), arbitrated
    per the CVP-1 source's write-order mechanism. The E-VTAGE-side
    params below are a DELIBERATE duplicate of EVtageVP's own params
    (same names, defaults, help text) rather than a shared mixin --
    the two SimObjects have independent lifetimes and this file is
    the single source of truth for both; a future E-VTAGE geometry
    change must be applied to both classes by hand (drift risk, noted
    here rather than hidden behind indirection).
    """

    type = "EvesVP"
    cxx_class = "gem5::o3::EvesVP"
    cxx_header = "cpu/o3/vp/eves.hh"

    baseEntries = Param.Unsigned(
        8192,
        "VT0 (tagged, 2-way skewed base component) TOTAL entries "
        "across both ways; must be even, and half must be a power "
        "of two",
    )
    taggedEntries = Param.Unsigned(
        1024,
        "Entries per tagged component (VT1..VTnumTagged); all tagged "
        "components share this size",
    )
    numTagged = Param.Unsigned(
        6,
        "Number of tagged components (VT1..VTnumTagged). The biased-"
        "rank token field packs 0 = none, 1 = VT0, 2..(1+numTagged) = "
        "VT1..VTnumTagged, so this must be <= 7",
    )
    historyLengths = VectorParam.Unsigned(
        [2, 4, 8, 16, 32, 64],
        "Per-tagged-component history length L(i), shortest to "
        "longest; size must equal numTagged, each length in [1, 128] "
        "(the history snapshot is 128 bits)",
    )
    baseTagBits = Param.Unsigned(
        12,
        "VT0's tag width; tagged component i's (1-based) tag width "
        "is baseTagBits + i",
    )
    confBits = Param.Unsigned(
        3, "Saturating confidence-counter width, every component"
    )
    confThreshold = Param.Unsigned(
        7,
        "Minimum confidence required to predict (minimum 1; 0 would "
        "make the verify-site corrective punish unable to leave an "
        "entry below threshold -- squash-livelock hazard -- and is "
        "rejected)",
    )
    uBits = Param.Unsigned(
        2, "Saturating usefulness-counter width, every component"
    )
    tickMax = Param.Unsigned(
        1024,
        "TICK aging-pass threshold (accumulates NA - 5*ALL after "
        "every allocation attempt; at this value every entry's "
        "nonzero usefulness counter is decremented and TICK resets)",
    )
    burstGuardWindow = Param.Unsigned(
        0,
        "Burst-misprediction guard: while fewer than this many "
        "instructions have been renamed since the last delivered "
        "E-VTAGE misprediction, prediction emission is suppressed "
        "(the lookup and commit training still happen). 0 = off "
        "(default, the ratified fork); 128 = CVP-1 EVES's own "
        "behavior.",
    )
    vtageOverwriteRequiresConfidence = Param.Bool(
        True,
        "EVES arbitration: require the embedded E-VTAGE side to be "
        "high-confidence before its value overwrites the stride "
        "prediction. True (default; the 190-checkpoint A/B winner by "
        "+3.6%) gates the overwrite on VTAGE confidence. False "
        "reproduces the CVP-1 source's write-order mechanism as this "
        "port maps it: a VTAGE tag hit outside the post-misprediction "
        "blackout overwrites even below confidence.",
    )
