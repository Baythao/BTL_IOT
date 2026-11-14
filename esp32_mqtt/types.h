#pragma once
#include <Arduino.h>
struct Snapshot {
  bool fire, gas, ready, fan, pump, buzzer, door;
  int adc;
  uint32_t uptime;
};
struct AlarmEvent {
  char id[72];
  char kind[8];
  int adc;
  uint32_t uptime;
};
