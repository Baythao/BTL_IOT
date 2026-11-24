#include <Arduino.h>
#include <Wire.h>
#include <ESP32Servo.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <time.h>
#include <esp_system.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <atomic>
#include "config.h"
#include "types.h"

// Giu nguyen chan, muc kich va logic cua code ban gui.
const int CHAN_LUA=14, CHAN_GAS=36, RELAY_QUAT=18, RELAY_BOM=21;
const int CHAN_COI=13, CHAN_SERVO=23, OLED_SDA=22, OLED_SCK=19;
const int MUC_BAT_QUAT=HIGH, MUC_BAT_BOM=HIGH;
// Phan lon module flame DO active-LOW. Xac minh bang Serial Monitor:
// Khong lua = 1, co lua = 0. Neu module cua ban nguoc lai, doi LOW thanh HIGH.
const int MUC_BAT_COI=HIGH, MUC_CO_LUA=LOW;
const int GAS_BAT=1200, GAS_TAT=900;
// 5s chi la thoi gian bo qua ADC luc boot, KHONG la lam nong/ hieu chuan MQ-2.
const uint32_t CHO_GAS_MS=5000, THOI_GIAN_CHAY_MS=10000;
const int GOC_DONG=0, GOC_MO=90;
Servo servoCua;
Adafruit_SSD1306 oled(128,64,&Wire,-1);
bool oledOK=false;
uint32_t batDau=0, lanDoc=0, lanHienThi=0, lucBatDauDot=0;
int luaDO=HIGH, gasADC=0;
bool gasSanSang=false, coGas=false, coLua=false, daKichHoatDot=false;
bool dangChay=false, quatBat=false, bomBat=false, coiBat=false, cuaMo=false;

QueueHandle_t stateQueue=nullptr, fireQueue=nullptr, gasQueue=nullptr;
std::atomic<bool> mqttOnline{false};
char bootID[18];
uint32_t eventSeq=0;
// Chi task mang duoc su dung mqtt/tls (PubSubClient khong thread-safe).
WiFiClientSecure tls;
WiFiClient wifiMqtt;
PubSubClient mqttSecure(tls);
PubSubClient mqttPlain(wifiMqtt);
PubSubClient* mqtt=nullptr;
String baseTopic, eventTopic, ackTopic, stateTopic, statusTopic;
// FIRE va GAS co su kien dang cho ACK rieng, khong chan nhau.
AlarmEvent pendingEvents[2]{};
bool hasPending[2]={false,false};
uint32_t lastEventSend[2]={0,0};

void ghiDauRa(int chan,int mucBat,bool bat) {
  digitalWrite(chan,bat?mucBat:!mucBat);
}
void khoiTaoDauRa(int chan,int mucBat) {
  digitalWrite(chan,!mucBat); pinMode(chan,OUTPUT); digitalWrite(chan,!mucBat);
  // Khong bao dam muc chan trong thoi gian reset/boot ROM; can dien tro keo
  // ve muc tat phu hop o mach ngoai neu relay bi nhay khi cap nguon.
}
void khoiTaoOLED() {
  Wire.begin(OLED_SDA,OLED_SCK); Wire.setTimeOut(20);
  uint8_t addr=0;
  for(uint8_t a: {uint8_t(0x3C),uint8_t(0x3D)}) {
    Wire.beginTransmission(a);
    if(Wire.endTransmission()==0) {addr=a; break;}
  }
  if(!addr) {Serial.println("Khong thay OLED"); return;}
  oledOK=oled.begin(SSD1306_SWITCHCAPVCC,addr,true,false);
  if(oledOK) {oled.setTextSize(1);oled.setTextColor(SSD1306_WHITE);oled.setTextWrap(false);}
}
void docCamBien(uint32_t now) {
  luaDO=digitalRead(CHAN_LUA); coLua=(luaDO==MUC_CO_LUA);
  static bool firstFireRead=true, previousFire=false;
  if(firstFireRead || coLua!=previousFire) {
    Serial.printf("CAM BIEN LUA: DO=%d, FIRE=%s (active=%d)\n",luaDO,coLua?"ON":"OFF",MUC_CO_LUA);
    previousFire=coLua; firstFireRead=false;
  }
  uint32_t sum=0; for(int i=0;i<10;i++) sum+=analogRead(CHAN_GAS);
  gasADC=sum/10;
  gasSanSang=(now-batDau>=CHO_GAS_MS);
  if(!gasSanSang) coGas=false;
  else if(gasADC>=GAS_BAT) coGas=true;
  else if(gasADC<=GAS_TAT) coGas=false;
}
void dieuKhien(uint32_t now) {
  if(!coLua) daKichHoatDot=false;
  else if(!daKichHoatDot) {daKichHoatDot=true;lucBatDauDot=now;}
  dangChay=coLua&&daKichHoatDot&&(now-lucBatDauDot<THOI_GIAN_CHAY_MS);
  quatBat=coGas||dangChay; coiBat=coGas||dangChay; bomBat=dangChay;
  if(cuaMo!=dangChay) {cuaMo=dangChay;servoCua.write(cuaMo?GOC_MO:GOC_DONG);}
  ghiDauRa(RELAY_QUAT,MUC_BAT_QUAT,quatBat);
  ghiDauRa(RELAY_BOM,MUC_BAT_BOM,bomBat);
  ghiDauRa(CHAN_COI,MUC_BAT_COI,coiBat);
}
bool enqueueAlarm(const char* kind,uint32_t now) {
  QueueHandle_t target=strcmp(kind,"FIRE")==0?fireQueue:gasQueue;
  if(!target) return false;
  AlarmEvent e{};
  snprintf(e.id,sizeof(e.id),"%s-%lu",bootID,(unsigned long)++eventSeq);
  snprintf(e.kind,sizeof(e.kind),"%s",kind);
  e.adc=gasADC; e.uptime=now;
  if(xQueueSend(target,&e,0)!=pdTRUE) {
    Serial.println("HANG DOI CANH BAO DAY - chua luu su kien moi");return false;
  }
  Serial.printf("Xep canh bao %s: %s\n",kind,e.id);return true;
}
void taoCanhBao(uint32_t now) {
  // FIRE va GAS doc lap: moi loai 1 su kien khi bat dau, rearm sau 3s an toan.
  // Chi loc thong bao; khong thay doi logic dieu khien tai cho.
  static bool sent[2]={false,false};
  static uint32_t lastActive[2]={0,0}, lastTry[2]={0,0};
  bool active[2]={coLua,coGas};
  for(int i=0;i<2;i++) {
    if(active[i]) {
      lastActive[i]=now;
      if(!sent[i]&&(lastTry[i]==0||now-lastTry[i]>=1000)) {
        lastTry[i]=now;sent[i]=enqueueAlarm(i==0?"FIRE":"GAS",now);
      }
    } else if(sent[i]&&now-lastActive[i]>=3000) sent[i]=false;
  }
}
void mqttCallback(char* topic,byte* payload,unsigned int length) {
  // ACK chi xac nhan PostgreSQL da luu; moi loai FIRE/GAS duoc xu ly rieng.
  if(String(topic)!=ackTopic) return;
  for(int i=0;i<2;i++) {
    if(hasPending[i] && length==strlen(pendingEvents[i].id)
       && memcmp(payload,pendingEvents[i].id,length)==0) {
      Serial.printf("Server da luu %s: %s\n",pendingEvents[i].kind,pendingEvents[i].id);
      hasPending[i]=false;
      return;
    }
  }
}

// Hai hang doi rieng: mot su kien GAS bi loi ACK khong chan FIRE.
void napSuKienDangCho() {
  QueueHandle_t queues[2]={fireQueue,gasQueue};
  for(int i=0;i<2;i++) {
    if(hasPending[i] || !queues[i]) continue;
    AlarmEvent next{};
    if(xQueueReceive(queues[i],&next,0)==pdTRUE) {
      pendingEvents[i]=next;
      hasPending[i]=true;
      lastEventSend[i]=millis()-1000UL; // Lan dau gui ngay.
    }
  }
}

void guiCanhBaoDangCho(uint32_t now) {
  for(int i=0;i<2;i++) {
    if(!hasPending[i] || now-lastEventSend[i]<1000UL) continue;
    lastEventSend[i]=now;
    const AlarmEvent &ev=pendingEvents[i];
    char payload[384];
    snprintf(payload,sizeof(payload),
      "{\"device\":\"%s\",\"id\":\"%s\",\"kind\":\"%s\",\"gas_adc\":%d,\"uptime_ms\":%lu,\"age_ms\":%lu}",
      DEVICE_ID,ev.id,ev.kind,ev.adc,
      (unsigned long)ev.uptime,(unsigned long)(now-ev.uptime));
    if(!mqtt->publish(eventTopic.c_str(),payload,false))
      Serial.printf("MQTT publish %s failed, retry in 1s\n",ev.kind);
    else Serial.printf("Da gui %s: %s\n",ev.kind,ev.id);
  }
}

void networkTask(void*) {
  baseTopic=String("fire-demo/")+DEVICE_ID;
  eventTopic=baseTopic+"/event"; ackTopic=baseTopic+"/ack";
  stateTopic=baseTopic+"/state"; statusTopic=baseTopic+"/status";
  Serial.printf("FIRE sensor active-level=%d; MQTT broker=%s:%d; device=%s\n",
                MUC_CO_LUA, MQTT_HOST, MQTT_PORT, DEVICE_ID);
  WiFi.mode(WIFI_STA); WiFi.setAutoReconnect(true); WiFi.begin(WIFI_SSID,WIFI_PASS);
  configTime(0,0,"pool.ntp.org","time.google.com");
  if(MQTT_TLS) {tls.setCACert(MQTT_ROOT_CA);tls.setHandshakeTimeout(5);mqtt=&mqttSecure;}
  else mqtt=&mqttPlain;
  mqtt->setServer(MQTT_HOST,MQTT_PORT); mqtt->setCallback(mqttCallback);
  mqtt->setBufferSize(768); mqtt->setSocketTimeout(3); mqtt->setKeepAlive(30);
  uint32_t lastWifi=millis(), lastConnect=millis()-3000UL;
  uint32_t lastState=millis()-750UL;
  Snapshot s{}; bool haveState=false;
  for(;;) {
    uint32_t now=millis();
    if(xQueueReceive(stateQueue,&s,0)==pdTRUE) haveState=true;
    if(WiFi.status()!=WL_CONNECTED) {
      mqttOnline=false;
      if(mqtt->connected()) mqtt->disconnect();
      if(now-lastWifi>=15000) {lastWifi=now;WiFi.reconnect();}
    } else if(!MQTT_TLS || time(nullptr)>1700000000) {
      if(!mqtt->connected()&&now-lastConnect>=3000) {
        lastConnect=now;
        String clientID=String(DEVICE_ID)+"-"+bootID;
        if(mqtt->connect(clientID.c_str(),MQTT_USER,MQTT_PASS,
              statusTopic.c_str(),1,true,"offline")) {
          mqtt->subscribe(ackTopic.c_str(),1);
          mqtt->publish(statusTopic.c_str(),"online",true);
          lastState=now-750UL;
          for(int i=0;i<2;i++) if(hasPending[i]) lastEventSend[i]=now-1000UL;
          Serial.printf("MQTT CONNECTED (%s)\n",MQTT_TLS?"TLS":"LAN plain");
        } else Serial.printf("MQTT loi=%d; kiem tra host/port/user/pass/firewall\n",mqtt->state());
      }
      mqtt->loop(); mqttOnline=mqtt->connected();
      if(mqtt->connected()) {
        // Nap va gui ca FIRE va GAS truoc telemetry, moi loai mot ACK rieng.
        napSuKienDangCho();
        guiCanhBaoDangCho(now);
        if(haveState&&now-lastState>=750) {
          lastState=now;char payload[600];
          snprintf(payload,sizeof(payload),
            "{\"fire\":%s,\"gas\":%s,\"gas_ready\":%s,\"gas_adc\":%d,\"fan\":%s,\"pump\":%s,\"buzzer\":%s,\"servo\":%d,\"uptime_ms\":%lu,\"config\":{\"gas_on\":%d,\"gas_off\":%d,\"gas_warmup_ms\":%lu,\"fire_run_ms\":%lu,\"fire_active_level\":%d}}",
            s.fire?"true":"false",s.gas?"true":"false",s.ready?"true":"false",s.adc,
            s.fan?"true":"false",s.pump?"true":"false",s.buzzer?"true":"false",
            s.door?90:0,(unsigned long)s.uptime,GAS_BAT,GAS_TAT,
            (unsigned long)CHO_GAS_MS,(unsigned long)THOI_GIAN_CHAY_MS,MUC_CO_LUA);
          mqtt->publish(stateTopic.c_str(),payload,false);
        }
      }
    } else mqttOnline=false; // Doi NTP trong task mang, loop dieu khien van chay
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}
void hienThi(uint32_t now) {
  Serial.printf("LUA_DO=%d | GAS=%d/%s | QUAT=%d BOM=%d COI=%d SERVO=%d | MQTT=%s\n",
    luaDO,gasADC,gasSanSang?(coGas?"BAO":"DUOI NGUONG"):"CHO",
    quatBat,bomBat,coiBat,cuaMo?90:0,mqttOnline.load()?"ON":"OFF");
  if(!oledOK) return;
  oled.clearDisplay();oled.setCursor(0,0);
  oled.println("MO HINH MQTT / 10s");
  oled.print("LUA: ");oled.println(coLua?"PHAT HIEN":"KHONG");
  oled.print("GAS: ");oled.print(gasADC);oled.println(!gasSanSang?" CHO":(coGas?" BAO":" THAP"));
  oled.print("QUAT:");oled.print(quatBat?"BAT":"TAT");oled.print(" BOM:");oled.println(bomBat?"BAT":"TAT");
  oled.print("COI: ");oled.println(coiBat?"BAT":"TAT");
  oled.print("SERVO: ");oled.println(cuaMo?90:0);
  oled.print("WIFI:");oled.print(WiFi.status()==WL_CONNECTED?"ON":"OFF");
  oled.print(" MQTT:");oled.println(mqttOnline.load()?"ON":"OFF");
  oled.println(coLua&&!dangChay?"HET 10s / VAN CO LUA":"CHI DUNG MO HINH");
  oled.display();
}
void setup() {
  khoiTaoDauRa(RELAY_QUAT,MUC_BAT_QUAT);
  khoiTaoDauRa(RELAY_BOM,MUC_BAT_BOM);khoiTaoDauRa(CHAN_COI,MUC_BAT_COI);
  Serial.begin(115200);
  pinMode(CHAN_LUA,INPUT_PULLUP);pinMode(CHAN_GAS,INPUT);
  analogReadResolution(12);analogSetPinAttenuation(CHAN_GAS,ADC_11db);
  servoCua.setPeriodHertz(50);servoCua.attach(CHAN_SERVO,500,2400);servoCua.write(GOC_DONG);
  batDau=millis();khoiTaoOLED();
  snprintf(bootID,sizeof(bootID),"%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());
  stateQueue=xQueueCreate(1,sizeof(Snapshot));
  fireQueue=xQueueCreate(16,sizeof(AlarmEvent));
  gasQueue=xQueueCreate(16,sizeof(AlarmEvent));
  if(stateQueue&&fireQueue&&gasQueue) {
    if(xTaskCreatePinnedToCore(networkTask,"mqtt-network",12288,nullptr,1,nullptr,0)!=pdPASS)
      Serial.println("LOI tao task MQTT; dieu khien tai cho van chay");
  } else Serial.println("LOI tao queue; MQTT khong hoat dong");
}
void loop() {
  uint32_t now=millis();
  if(now-lanDoc>=50) {lanDoc=now;docCamBien(now);taoCanhBao(now);}
  dieuKhien(now);
  if(now-lanHienThi>=500) {
    lanHienThi=now;hienThi(now);
    Snapshot s{coLua,coGas,gasSanSang,quatBat,bomBat,coiBat,cuaMo,gasADC,now};
    if(stateQueue) xQueueOverwrite(stateQueue,&s);
  }
  delay(1);
}
