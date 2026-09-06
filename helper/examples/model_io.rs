//! Print a Piper model's ONNX inputs and outputs.
//! Run: cargo run --example model_io -- ../assets/lessac-medium.onnx

use ort::session::Session;

fn main() {
    let path = std::env::args().nth(1).expect("usage: model_io <model.onnx>");
    let session = Session::builder()
        .expect("builder")
        .commit_from_file(&path)
        .expect("load model");
    println!("model: {path}");
    for input in session.inputs() {
        println!("  input  {} : {:?}", input.name(), input.dtype());
    }
    for output in session.outputs() {
        println!("  output {} : {:?}", output.name(), output.dtype());
    }
}
