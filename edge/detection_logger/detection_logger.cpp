#include <iostream>
#include <vector>
#include <chrono>
#include <iomanip>

#include <rpicam-apps/post_processing_stages/object_detect.hpp>
#include <rpicam-apps/post_processing_stages/post_processing_stage.hpp>

class DetectionLogger : public PostProcessingStage
{
public:
    DetectionLogger(RPiCamApp *app)
        : PostProcessingStage(app)
    {
    }

    char const *Name() const override
    {
        return "detection_logger";
    }

    bool Process(CompletedRequestPtr &request) override
    {
        std::vector<Detection> detections;

        if (request->post_process_metadata.Get(
                "object_detect.results", detections) != 0)
        {
            return false;
        }

        // Unix time (milliseconds)
        auto now = std::chrono::system_clock::now();
        auto timestamp =
            std::chrono::duration_cast<std::chrono::milliseconds>(
                now.time_since_epoch()).count();

        std::cout
            << "{\"timestamp\":" << timestamp
            << ",\"detections\":[";

        for (std::size_t i = 0; i < detections.size(); ++i)
        {
            const auto &d = detections[i];

            if (i > 0)
                std::cout << ",";

            std::cout
                << "{"
                << "\"class\":\"" << d.name << "\","
                << "\"category\":" << d.category << ","
                << "\"confidence\":"
                << std::fixed << std::setprecision(6)
                << d.confidence << ","
                << "\"bbox\":{"
                << "\"x\":" << d.box.x << ","
                << "\"y\":" << d.box.y << ","
                << "\"width\":" << d.box.width << ","
                << "\"height\":" << d.box.height
                << "}"
                << "}";
        }

        std::cout << "]}" << std::endl;

        return false;
    }
};

static PostProcessingStage *CreateDetectionLogger(RPiCamApp *app)
{
    return new DetectionLogger(app);
}

static RegisterStage register_stage(
    "detection_logger",
    &CreateDetectionLogger
);

