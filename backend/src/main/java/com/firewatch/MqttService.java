package com.firewatch;

import com.firewatch.model.AlarmEvent;
import com.firewatch.model.Device;
import com.firewatch.model.Repos;
import jakarta.annotation.PreDestroy;
import org.eclipse.paho.client.mqttv3.*;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.*;

/**
 * Nhan du lieu tu ESP32 qua topic fire-demo/{deviceId}/{state|event|status}.
 * Chi chay 1 ban backend (client id co dinh), giong server Python cu.
 */
@Service
public class MqttService implements MqttCallbackExtended {
    private final Repos.Devices devices;
    private final Repos.Events events;
    private final ObjectMapper json;
    private final String url, user, pass;
    private MqttClient client;

    public MqttService(Repos.Devices devices, Repos.Events events, ObjectMapper json,
                       @Value("${mqtt.url}") String url,
                       @Value("${mqtt.user}") String user,
                       @Value("${mqtt.pass}") String pass) {
        this.devices = devices;
        this.events = events;
        this.json = json;
        this.url = url;
        this.user = user;
        this.pass = pass;
    }

    /** Ket noi trong luong rieng, thu lai moi 5 giay neu broker chua chay. */
    @EventListener(ApplicationReadyEvent.class)
    public void start() {
        new Thread(() -> {
            while (true) {
                try {
                    client = new MqttClient(url, "firewatch-backend", new MemoryPersistence());
                    client.setCallback(this);
                    MqttConnectOptions opt = new MqttConnectOptions();
                    opt.setUserName(user);
                    opt.setPassword(pass.toCharArray());
                    opt.setAutomaticReconnect(true);
                    opt.setCleanSession(true);
                    opt.setKeepAliveInterval(30);
                    client.connect(opt);
                    return;
                } catch (MqttException e) {
                    System.out.println("MQTT chua ket noi duoc (" + e.getMessage() + "), thu lai sau 5s");
                    try { Thread.sleep(5000); } catch (InterruptedException ie) { return; }
                }
            }
        }, "mqtt-connect").start();
    }

    @PreDestroy
    public void stop() throws MqttException {
        if (client != null && client.isConnected()) client.disconnect();
    }

    @Override
    public void connectComplete(boolean reconnect, String serverURI) {
        try {
            client.subscribe(new String[]{"fire-demo/+/state", "fire-demo/+/event", "fire-demo/+/status"},
                             new int[]{0, 1, 1});
            System.out.println("MQTT da ket noi: " + serverURI);
        } catch (MqttException e) {
            System.out.println("Loi subscribe: " + e.getMessage());
        }
    }

    @Override
    public void connectionLost(Throwable cause) {
        System.out.println("Mat ket noi MQTT, dang tu ket noi lai...");
    }

    @Override
    public void deliveryComplete(IMqttDeliveryToken token) {}

    @Override
    public void messageArrived(String topic, MqttMessage msg) {
        // Moi loi phai bat lai o day, neu khong Paho se ngat ket noi
        try {
            String[] parts = topic.split("/");
            if (parts.length != 3 || msg.getPayload().length > 2048) return;
            String deviceId = parts[1], type = parts[2];

            Device d = devices.findById(deviceId).orElse(null);
            if (d == null || !d.status.equals("ACTIVE")) {
                System.out.println("Bo qua du lieu tu thiet bi chua kich hoat: " + deviceId);
                return;
            }
            String body = new String(msg.getPayload(), StandardCharsets.UTF_8);

            switch (type) {
                case "state" -> {
                    if (msg.isRetained()) return;      // du lieu cu, khong coi la moi
                    checkState(body);
                    devices.saveState(deviceId, body);
                }
                case "status" -> {
                    if (!body.equals("online") && !body.equals("offline")) return;
                    devices.saveOnline(deviceId, body.equals("online"));
                }
                case "event" -> {
                    if (msg.isRetained()) return;
                    Map<?, ?> e = json.readValue(body, Map.class);
                    String id = String.valueOf(e.get("id"));
                    String kind = String.valueOf(e.get("kind"));
                    if (!id.matches("[a-zA-Z0-9_-]{1,72}") || !(kind.equals("FIRE") || kind.equals("GAS"))) return;

                    if (!events.existsById(id)) {       // ESP32 gui lai -> khong luu trung
                        AlarmEvent a = new AlarmEvent();
                        a.id = id;
                        a.deviceId = deviceId;
                        a.kind = kind;
                        a.gasAdc = ((Number) e.get("gas_adc")).intValue();
                        a.ageMs = ((Number) e.get("age_ms")).longValue();
                        events.save(a);
                        System.out.println("CANH BAO " + kind + " tu " + deviceId);
                    }
                    // ACK sau khi da luu DB, ESP32 se ngung gui lai
                    client.publish("fire-demo/" + deviceId + "/ack", id.getBytes(StandardCharsets.UTF_8), 1, false);
                }
                default -> { }
            }
        } catch (Exception e) {
            System.out.println("Du lieu MQTT khong hop le tren " + topic + ": " + e.getMessage());
        }
    }

    /** Kiem tra ban tin /state dung dinh dang truoc khi luu. */
    private void checkState(String body) {
        Map<?, ?> s = json.readValue(body, Map.class);
        for (String key : List.of("fire", "gas", "gas_ready", "fan", "pump", "buzzer")) {
            if (!(s.get(key) instanceof Boolean)) throw new IllegalArgumentException("thieu " + key);
        }
        for (String key : List.of("gas_adc", "servo", "uptime_ms")) {
            if (!(s.get(key) instanceof Number)) throw new IllegalArgumentException("thieu " + key);
        }
    }
}
