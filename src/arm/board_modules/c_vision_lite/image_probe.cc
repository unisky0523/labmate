#include <sys/resource.h>

#include <algorithm>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include "paddle_api.h"

using paddle::lite_api::CreatePaddlePredictor;
using paddle::lite_api::MobileConfig;

long peak_rss_kib() {
  struct rusage usage {};
  getrusage(RUSAGE_SELF, &usage);
  return usage.ru_maxrss;
}

std::vector<int> parse_roi(const std::string& text) {
  std::vector<int> result;
  size_t start = 0;
  while (start < text.size()) {
    size_t end = text.find(',', start);
    result.push_back(std::stoi(text.substr(start, end - start)));
    if (end == std::string::npos) break;
    start = end + 1;
  }
  if (result.size() != 4 || result[2] <= 0 || result[3] <= 0)
    throw std::invalid_argument("ROI must be x,y,w,h");
  return result;
}

std::vector<std::string> read_alphabet(const std::string& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open alphabet: " + path);
  std::vector<std::string> alphabet;
  std::string symbol;
  while (std::getline(input, symbol, '\0')) alphabet.push_back(symbol);
  return alphabet;
}

std::string json_escape(const std::string& value) {
  std::ostringstream out;
  for (unsigned char c : value) {
    if (c == '"' || c == '\\') out << '\\' << c;
    else if (c == '\n') out << "\\n";
    else out << c;
  }
  return out.str();
}

int main(int argc, char** argv) {
  if (argc != 5 && argc != 6) {
    std::cerr << "usage: labmate_lite_image_probe MODEL.nb IMAGE X,Y,W,H ALPHABET.bin [OUTPUT.json]\n";
    return 2;
  }
  try {
    const auto roi = parse_roi(argv[3]);
    const cv::Mat source = cv::imread(argv[2], cv::IMREAD_COLOR);
    if (source.empty()) throw std::runtime_error("cannot read image");
    const cv::Rect bounds(0, 0, source.cols, source.rows);
    const cv::Rect requested(roi[0], roi[1], roi[2], roi[3]);
    const cv::Rect clipped = requested & bounds;
    if (clipped.width < 2 || clipped.height < 2)
      throw std::runtime_error("ROI is outside image");
    cv::Mat crop = source(clipped), gray, resized;
    cv::cvtColor(crop, gray, cv::COLOR_BGR2GRAY);
    const float scale = 48.0F / static_cast<float>(gray.rows);
    cv::resize(gray, resized,
               cv::Size(std::max(1, static_cast<int>(gray.cols * scale)), 48),
               0, 0, scale < 1.0F ? cv::INTER_AREA : cv::INTER_CUBIC);
    cv::Mat canvas(48, 320, CV_8UC1, cv::Scalar(0));
    const int width = std::min(320, resized.cols);
    resized(cv::Rect(0, 0, width, 48)).copyTo(canvas(cv::Rect(0, 0, width, 48)));

    MobileConfig config;
    config.set_model_from_file(argv[1]);
    auto predictor = CreatePaddlePredictor<MobileConfig>(config);
    auto input = predictor->GetInput(0);
    input->Resize({1, 3, 48, 320});
    float* data = input->mutable_data<float>();
    for (int y = 0; y < 48; ++y) {
      for (int x = 0; x < 320; ++x) {
        const float value = canvas.at<unsigned char>(y, x) / 255.0F;
        for (int c = 0; c < 3; ++c) data[c * 48 * 320 + y * 320 + x] = value;
      }
    }
    const auto begin = std::chrono::steady_clock::now();
    if (!predictor->Run()) throw std::runtime_error("Lite inference failed");
    const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - begin).count();
    const auto output = predictor->GetOutput(0);
    const auto shape = output->shape();
    if (shape.size() != 3 || shape[0] != 1) throw std::runtime_error("unexpected output shape");
    const auto alphabet = read_alphabet(argv[4]);
    if (shape[2] != static_cast<int64_t>(alphabet.size()))
      throw std::runtime_error("alphabet does not match model output");
    std::string text;
    float score_sum = 0.0F;
    int count = 0, previous = 0;
    const float* probabilities = output->data<float>();
    for (int64_t t = 0; t < shape[1]; ++t) {
      const float* row = probabilities + t * shape[2];
      const int index = static_cast<int>(std::max_element(row, row + shape[2]) - row);
      if (index != 0 && index != previous) {
        text += alphabet[index];
        score_sum += row[index];
        ++count;
      }
      previous = index;
    }
    std::ostringstream json;
    json << "{\"valid\":" << (text.empty() ? "false" : "true")
         << ",\"text\":\"" << json_escape(text) << "\",\"confidence\":"
         << std::fixed << std::setprecision(4) << (count ? score_sum / count : 0.0F)
         << ",\"inference_ms\":" << elapsed
         << ",\"peak_rss_kib\":" << peak_rss_kib()
         << ",\"roi\":\"" << argv[3] << "\"}";
    std::cout << json.str() << '\n';
    if (argc == 6) {
      std::ofstream saved(argv[5]);
      if (!saved) throw std::runtime_error("cannot write JSON output");
      saved << json.str() << '\n';
    }
    return text.empty() ? 3 : 0;
  } catch (const std::exception& error) {
    std::cerr << "image probe failed: " << error.what() << '\n';
    return 1;
  }
}
