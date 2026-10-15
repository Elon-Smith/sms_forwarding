#pragma once
#include <stdint.h>

// 对外卡号固定为 1/2；对象和任务显式保存卡号，不依赖全局选卡。
using IdfModemId = uint8_t;
constexpr IdfModemId IDF_SIM1 = 1;
constexpr IdfModemId IDF_SIM2 = 2;
constexpr unsigned IDF_MODEM_COUNT = 2;
constexpr bool idf_modem_id_valid(IdfModemId id) { return id >= 1 && id <= IDF_MODEM_COUNT; }
struct IdfModemPins { int uart; int tx; int rx; int en; };
constexpr IdfModemPins IDF_MODEM_PINS[IDF_MODEM_COUNT] = {{1, 3, 4, 5}, {0, 6, 7, 10}};
constexpr bool idf_board_pins_valid()
{
    int pins[6] = {IDF_MODEM_PINS[0].tx, IDF_MODEM_PINS[0].rx, IDF_MODEM_PINS[0].en,
                   IDF_MODEM_PINS[1].tx, IDF_MODEM_PINS[1].rx, IDF_MODEM_PINS[1].en};
    for (const auto& modem : IDF_MODEM_PINS) if (modem.uart < 0 || modem.uart > 1) return false;
    if (IDF_MODEM_PINS[0].uart == IDF_MODEM_PINS[1].uart) return false;
    for (unsigned i = 0; i < 6; ++i) {
        if (pins[i] < 0 || pins[i] > 10 || pins[i] == 2 || pins[i] == 8 || pins[i] == 9) return false;
        for (unsigned j = 0; j < i; ++j) if (pins[i] == pins[j]) return false;
    }
    return true;
}
static_assert(idf_board_pins_valid(), "Modem pins conflict with each other, boot straps, LED or USB");

#ifdef ESP_PLATFORM
#include "sdkconfig.h"
#if !CONFIG_IDF_TARGET_ESP32C3 || !CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
#error "Dual modem board requires ESP32-C3 and USB Serial/JTAG console; UART0 belongs to SIM2"
#endif
#endif
