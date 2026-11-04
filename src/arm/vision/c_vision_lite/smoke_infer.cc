#include <sys/resource.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "paddle_api.h"

using paddle::lite_api::CreatePaddlePredictor;
using paddle::lite_api::MobileConfig;
using paddle::lite_api::PaddlePredictor;
using paddle::lite_api::shape_t;

std::vector<int64_t> ParseShape(const std::string& text) {
  std::vector<int64_t> shape;
  size_t start = 0;
  while (start < text.size()) {
    const size_t end = text.find(',', start);
    const std::string part = text.substr(start, end - start);
    const auto dimension = std::stoll(part);
    if (dimension <= 0) throw std::invalid_argument("Dimensions must be positive");
    shape.push_back(dimension);
    if (end == std::string::npos) break;
    start = end + 1;
  }
  if (shape.size() != 4) throw std::invalid_argument("Expected N,C,H,W input shape");
  return shape;
}

long PeakRssKiB() {
  struct rusage usage {};
  getrusage(RUSAGE_SELF, &usage);
  return usage.ru_maxrss;
}

int main(int argc, char** argv) {
  if (argc != 3 && argc != 5 && argc != 6) {
    std::cerr << "Usage: smoke_infer MODEL.nb N,C,H,W [INPUT_F32 OUTPUT_F32 [ALPHABET_BIN]]\n";
    return 2;
  }
  try {
    std::cerr << "stage=create_predictor_begin\n" << std::flush;
    MobileConfig config;
    config.set_model_from_file(argv[1]);
    auto predictor = CreatePaddlePredictor<MobileConfig>(config);
    std::cerr << "stage=create_predictor_done\n" << std::flush;
    std::cout << "predictor_peak_rss_kib=" << PeakRssKiB() << '\n' << std::flush;
    const std::vector<int64_t> shape = ParseShape(argv[2]);
    auto input = predictor->GetInput(0);
    input->Resize(shape);
    size_t elements = 1;
    for (auto dimension : shape) elements *= static_cast<size_t>(dimension);
    float* data = input->mutable_data<float>();
    if (argc >= 5) {
      std::ifstream source(argv[3], std::ios::binary | std::ios::ate);
      if (!source) throw std::runtime_error("Cannot open input tensor");
      if (source.tellg() != static_cast<std::streamoff>(elements * sizeof(float))) {
        throw std::runtime_error("Input tensor byte count does not match shape");
      }
      source.seekg(0);
      source.read(reinterpret_cast<char*>(data), elements * sizeof(float));
      if (!source) throw std::runtime_error("Cannot read input tensor");
    } else {
      for (size_t index = 0; index < elements; ++index) data[index] = 0.0f;
    }
    std::cout << "input_peak_rss_kib=" << PeakRssKiB() << '\n' << std::flush;

    const auto begin = std::chrono::steady_clock::now();
    std::cerr << "stage=run_begin\n" << std::flush;
    predictor->Run();
    std::cerr << "stage=run_done\n" << std::flush;
    const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - begin);
    const auto names = predictor->GetOutputNames();
    if (names.empty()) throw std::runtime_error("Model produced no outputs");
    for (size_t index = 0; index < names.size(); ++index) {
      const auto output = predictor->GetOutput(index);
      std::cout << "output " << index << " shape:";
      for (auto dimension : output->shape()) std::cout << ' ' << dimension;
      std::cout << '\n';
    }
    if (argc >= 5) {
      const auto output = predictor->GetOutput(0);
      size_t count = 1;
      for (auto dimension : output->shape()) count *= static_cast<size_t>(dimension);
      std::ofstream destination(argv[4], std::ios::binary);
      if (!destination) throw std::runtime_error("Cannot create output tensor");
      destination.write(reinterpret_cast<const char*>(output->data<float>()),
                        count * sizeof(float));
      if (!destination) throw std::runtime_error("Cannot write output tensor");
      if (argc == 6) {
        std::ifstream dictionary(argv[5], std::ios::binary);
        if (!dictionary) throw std::runtime_error("Cannot open alphabet");
        std::vector<std::string> alphabet;
        std::string symbol;
        while (std::getline(dictionary, symbol, '\0')) alphabet.push_back(symbol);
        const auto dims = output->shape();
        if (dims.size() != 3 || dims[0] != 1 ||
            dims[2] != static_cast<int64_t>(alphabet.size())) {
          throw std::runtime_error("CTC output shape does not match alphabet");
        }
        const float* probabilities = output->data<float>();
        std::string decoded;
        double total_score = 0.0;
        size_t character_count = 0;
        int64_t previous = 0;
        for (int64_t time = 0; time < dims[1]; ++time) {
          const float* row = probabilities + time * dims[2];
          const int64_t index = std::max_element(row, row + dims[2]) - row;
          if (index != 0 && index != previous) {
            decoded += alphabet[index];
            total_score += row[index];
            ++character_count;
          }
          previous = index;
        }
        std::cout << "decoded_text=" << decoded << " score="
                  << (character_count ? total_score / character_count : 0.0) << '\n';
      }
    }
    std::cout << "first_run_ms=" << elapsed.count()
              << " maxrss_kib=" << PeakRssKiB() << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "Smoke inference failed: " << error.what() << '\n';
    return 1;
  }
}
