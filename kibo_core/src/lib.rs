use pyo3::prelude::*;
use pyo3::types::PyBytes;

/// High-performance chroma-key with soft-edge anti-aliasing and colour despill.
///
/// Processes BGRA pixel data (QImage Format_ARGB32 byte order on little-endian).
/// Returns new BGRA bytes with background pixels made transparent.
///
/// Algorithm:
///   1. Sample background colour from pixel (0,0).
///   2. For each pixel, compute max-channel distance from background.
///   3. distance < core_threshold  → fully transparent (alpha = 0)
///   4. core_threshold ≤ distance < edge_threshold → soft alpha fade + despill
///   5. distance ≥ edge_threshold  → keep as-is (foreground)
#[pyfunction]
#[pyo3(signature = (data, width, height, core_threshold=50, edge_threshold=105))]
fn chroma_key<'py>(
    py: Python<'py>,
    data: &[u8],
    width: u32,
    height: u32,
    core_threshold: i16,
    edge_threshold: i16,
) -> PyResult<Bound<'py, PyBytes>> {
    let pixel_count = (width * height) as usize;
    let expected_len = pixel_count * 4;

    if data.len() != expected_len {
        return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
            "Expected {} bytes ({}x{}x4), got {}",
            expected_len, width, height, data.len()
        )));
    }

    let mut out = data.to_vec();

    // Background colour from top-left pixel (BGRA order)
    let bg_b = data[0] as i16;
    let bg_g = data[1] as i16;
    let bg_r = data[2] as i16;

    // Determine dominant background channel for despill
    let dom_idx: usize = if bg_b >= bg_g && bg_b >= bg_r {
        0
    } else if bg_g >= bg_r {
        1
    } else {
        2
    };
    let other_indices: [usize; 2] = match dom_idx {
        0 => [1, 2],
        1 => [0, 2],
        _ => [0, 1],
    };

    let span = (edge_threshold - core_threshold) as f32;

    for i in 0..pixel_count {
        let offset = i * 4;
        let b = out[offset] as i16;
        let g = out[offset + 1] as i16;
        let r = out[offset + 2] as i16;

        let diff_b = (b - bg_b).abs();
        let diff_g = (g - bg_g).abs();
        let diff_r = (r - bg_r).abs();
        let max_diff = diff_b.max(diff_g).max(diff_r);

        if max_diff < core_threshold {
            // Core background → fully transparent
            out[offset + 3] = 0;
        } else if max_diff < edge_threshold {
            // Fringe zone → soft alpha edge
            let alpha_factor = (max_diff - core_threshold) as f32 / span;
            let current_alpha = out[offset + 3] as f32;
            out[offset + 3] = (current_alpha * alpha_factor) as u8;

            // Despill: clamp dominant channel to average of other two
            let avg_others = ((out[offset + other_indices[0]] as u16
                + out[offset + other_indices[1]] as u16)
                / 2) as u8;
            if out[offset + dom_idx] > avg_others {
                out[offset + dom_idx] = avg_others;
            }
        }
        // else: foreground — keep as-is
    }

    Ok(PyBytes::new(py, &out))
}

/// KIBO native performance module.
#[pymodule]
fn kibo_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(chroma_key, m)?)?;
    Ok(())
}
