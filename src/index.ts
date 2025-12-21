import { display } from "./device/display";
import Battery from "./device/battery";
import ChatFlow from "./core/ChatFlow";
import { telegramBot } from "./utils/telegram"; // Ensure telegram bot is initialized
import { startEsp32VoiceGateway } from "./device/esp32-voice";

const battery = new Battery();
battery.connect().catch(e => {
  console.error("fail to connect to battery service:", e);
});
battery.addListener("batteryLevel", (data: any) => {
  display({
    battery_level: data,
    });
});

const chatFlow = new ChatFlow();

// ESP32 BLE voice gateway -> inject audio into ChatFlow
startEsp32VoiceGateway((evt) => {
  chatFlow.handleExternalAudioFile(evt.path);
});
