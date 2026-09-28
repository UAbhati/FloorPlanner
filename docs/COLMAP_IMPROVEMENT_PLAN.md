# COLMAP Improvement Plan

**Goal:** Make photo/video tiers work autonomously without requiring GT, using only COLMAP SfM.

**Current Status:** COLMAP fails with "too thin" (< 200 reconstructed points), falling back to GT dimensions.

---

## Current State Analysis

### Existing Data
| Room | Photos | Video Duration | Frames Extracted (current) |
|------|--------|----------------|---------------------------|
| my_room (hall) | 17 | 58 sec | 16 (3.6s interval) |
| my_bedroom | 12 | ~45 sec | 16 (2.8s interval) |
| my_kitchen | 12 | ~40 sec | 16 (2.5s interval) |

### Current COLMAP Parameters
```python
# Feature extraction: Default SIFT, single_camera=1, no GPU
# Matching: Exhaustive matcher, no GPU
# Mapper settings (relaxed for indoor):
--Mapper.init_min_num_inliers 50
--Mapper.init_min_tri_angle 4
--Mapper.abs_pose_min_num_inliers 15
--Mapper.abs_pose_min_inlier_ratio 0.15
```

### Why It Fails
1. **Too few reconstructed points** (< 200 threshold)
2. **Sparse frame sampling** (16 frames from 58sec video = 1 frame per 3.6s)
3. **Limited overlap** between consumer phone photos
4. **Default SIFT features** may miss texture in plain walls
5. **No GPU acceleration** (slower, may timeout)

---

## Improvement Strategy

### Phase 1: Increase Frame Density (Quick Win)
**Goal:** Extract more video frames for better feature overlap

**Changes:**
- Increase `max_frames` from 16 → **60-100 frames**
- Calculate optimal FPS: `fps = 2-3` (captures every 0.3-0.5s)
- For 58sec video: 2fps × 58s = **116 frames**

**Pros:**
- More overlap between consecutive frames
- Better motion estimation
- No new captures needed

**Cons:**
- Slower COLMAP processing
- More disk space (60-100 JPEGs per video)

**Implementation:**
```python
# capture_io/android_media.py
def extract_video_frames(video_path, out_dir, max_frames=100):  # 16 → 100
    fps = max(2.0, max_frames / max(duration, 1e-3))  # minimum 2 FPS
```

---

### Phase 2: Improve Feature Matching
**Goal:** Better feature detection and matching

**Changes:**
1. **SIFT parameters:**
   ```bash
   --SiftExtraction.max_num_features 8192  # default 8192, try 16384
   --SiftExtraction.first_octave -1        # detect smaller features
   ```

2. **Sequential matcher** (instead of exhaustive) for video:
   ```bash
   colmap sequential_matcher  # assumes temporal order
   --SequentialMatching.overlap 10  # match with 10 neighbors
   --SequentialMatching.loop_detection 1  # detect loops
   ```

3. **Vocabulary tree matcher** (if sequential still fails):
   ```bash
   colmap vocab_tree_matcher --vocab_tree_path /path/to/vocab_tree.bin
   ```

**Pros:**
- Better features in texture-poor indoor scenes
- Sequential matching faster + more robust for video
- Loop detection helps with panoramic sweeps

**Cons:**
- May need to download vocabulary tree (~200MB)
- Still may fail on very plain walls

---

### Phase 3: Relax Reconstruction Thresholds
**Goal:** Accept sparser reconstructions

**Changes:**
1. **Lower point threshold:**
   ```python
   if len(points) < 200:  # Currently fails here
   # Change to:
   if len(points) < 100:  # More lenient
   ```

2. **Lower wall band threshold:**
   ```python
   if len(wall_band) < 50:  # Currently fails here
   # Change to:
   if len(wall_band) < 30:
   ```

3. **Add confidence flag:**
   ```python
   room.low_confidence = True if len(points) < 200 else False
   ```

**Pros:**
- Works with sparser captures
- Still get rough dimensions

**Cons:**
- Lower accuracy
- Need to document confidence levels

---

### Phase 4: Hybrid Fallback Strategy
**Goal:** Graceful degradation instead of complete failure

**Cascade:**
1. Try COLMAP with 100 frames
2. If < 200 points but ≥ 100: Use result, mark `low_confidence=True`
3. If < 100 points: Try sequential matcher
4. If still fails: Require user to provide **one dimension** via `--ref-length-m`
5. Last resort: GT lookup (but document this as benchmark mode)

**Output:**
```json
{
  "method_used": "colmap_sparse",
  "confidence": "low",
  "points_reconstructed": 156,
  "scale_source": "automatic"  // vs "user_provided" or "ground_truth"
}
```

---

## What We Need From You

### Option A: Use Existing Data (Recommended First)
- ✅ No action needed initially
- We'll try improving with current 17 photos + 58sec video
- Test if denser frame extraction (60-100 frames) is sufficient

### Option B: Capture Additional Data (If Phase 1 Fails)
For **each room** (hall, bedroom, kitchen):

**Photo Guidelines:**
- Take **25-30 photos** (currently have 12-17)
- Stand in different positions (~1m apart)
- Capture overlapping views (each feature should appear in 3+ photos)
- Include corners, walls, ceiling, floor
- Good lighting, avoid motion blur

**Video Guidelines:**
- Record **60-90 seconds** (currently have 40-60s)
- Walk slowly (~1 step per 2-3 seconds)
- Smooth panning, avoid sudden movements
- Hold phone steady (use both hands)
- Cover all walls + corners

**Why More Data Helps:**
- More features to match
- Better camera pose estimation
- Reduces "too thin" failures

---

## Implementation Plan

### Step 1: Test with Current Data (No New Captures)
1. Increase `max_frames` 16 → 100
2. Use sequential matcher for video
3. Lower thresholds to 100 points
4. Run on all 3 rooms (hall, bedroom, kitchen)
5. Measure success rate

**Expected Outcome:**
- ✅ If ≥ 100 points: Mark TODO complete
- ⚠️ If 50-100 points: Works but low confidence
- ❌ If < 50 points: Need Phase 2

### Step 2: Feature Matching Improvements (If Step 1 Fails)
1. Add SIFT parameter tuning
2. Try vocabulary tree matcher
3. Re-test on all rooms

### Step 3: Request More Captures (Only If Needed)
- Ask user for denser photos/video per guidelines above
- Re-run pipeline

### Step 4: Documentation Updates
- Update README with COLMAP requirements
- Add confidence levels to schema
- Document fallback cascade
- Remove `--no-colmap` from benchmark scripts

---

## Success Criteria

### Must Have:
- ✅ COLMAP reconstructs ≥ 100 points from video
- ✅ Room polygon extracted (even if sparse)
- ✅ One dimension still needed for metric scaling (honest limitation)
- ✅ Confidence flag in output JSON

### Nice to Have:
- ✅ ≥ 200 points (high confidence)
- ✅ Works on new rooms without GT
- ✅ Automatic scale from detected objects (future work)

### Known Limitations (Document Honestly):
- ⚠️ Still requires **one reference dimension** for metric scaling
- ⚠️ May fail on completely texture-less white walls
- ⚠️ GPU acceleration helps but not required

---

## Timeline Estimate

| Phase | Effort | Depends On |
|-------|--------|------------|
| Phase 1: Frame density | 1-2 hours | None (use existing data) |
| Phase 2: Feature matching | 2-3 hours | Phase 1 results |
| Phase 3: Threshold tuning | 1 hour | Phase 2 results |
| Phase 4: Fallback strategy | 2 hours | All above |
| Documentation | 1 hour | Final results |
| **Total** | **6-9 hours** | - |

---

## Questions for You

1. **Should we start with Phase 1** (denser frames, existing data) and see how far we get?
2. **Are you willing to capture more photos/video** if Phase 1 doesn't work?
3. **Is accepting "needs one dimension" acceptable**, or must it be 100% autonomous?
4. **For 3-room stitch**: Should we generalize it or keep property-specific for now?

---

## Next Steps (Your Decision)

- [ ] Approve this plan
- [ ] Answer questions above
- [ ] I'll update TODO.md with these tasks
- [ ] Start implementation (or wait for your go-ahead)
