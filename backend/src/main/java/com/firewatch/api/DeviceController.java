package com.firewatch.api;

import com.firewatch.model.AlarmEvent;
import com.firewatch.model.Device;
import com.firewatch.model.Repos;
import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.*;
import tools.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.*;

/** Xem du lieu thiet bi: trang thai, nguong, lich su canh bao. */
@RestController
@RequestMapping("/api")
public class DeviceController {
    private final Repos.Events events;
    private final Access access;
    private final ObjectMapper json;

    public DeviceController(Repos.Events events, Access access, ObjectMapper json) {
        this.events = events;
        this.access = access;
        this.json = json;
    }

    @GetMapping("/device/status")
    public Map<String, Object> status(HttpSession s, @RequestParam(required = false) String device) {
        Device d = access.allowedDevice(access.need(s, "view_status"), device);
        Map<String, Object> r = Json.state(d);
        Map<String, Object> data = payload(d);
        if (data != null) data.remove("config");       // nguong chi cho nguoi co quyen view_thresholds
        r.put("data", data);
        return r;
    }

    @GetMapping("/device/thresholds")
    public Map<String, Object> thresholds(HttpSession s, @RequestParam(required = false) String device) {
        Device d = access.allowedDevice(access.need(s, "view_thresholds"), device);
        Map<String, Object> data = payload(d);
        Map<String, Object> r = Json.state(d);
        r.put("config", data == null ? null : data.get("config"));
        r.put("source", "ESP32");
        return r;
    }

    @GetMapping("/history")
    public Map<String, Object> history(HttpSession s, @RequestParam(required = false) String device,
                                       @RequestParam(required = false) Double before) {
        Device d = access.allowedDevice(access.need(s, "view_history"), device);
        Instant until = before == null ? Instant.now().plusSeconds(1) : Instant.ofEpochMilli((long) (before * 1000));
        List<Map<String, Object>> rows = new ArrayList<>();
        for (AlarmEvent e : events.findTop100ByDeviceIdAndReceivedAtBeforeOrderByReceivedAtDesc(d.deviceId, until)) {
            Map<String, Object> p = Map.of("device", e.deviceId, "kind", e.kind, "gas_adc", e.gasAdc, "age_ms", e.ageMs);
            rows.add(Map.of("id", e.id, "received", Json.sec(e.receivedAt), "payload", p, "deliveries", List.of()));
        }
        return Map.of("events", rows, "activities", List.of());
    }

    /** Ban tin /state moi nhat cua thiet bi, dang Map. */
    @SuppressWarnings("unchecked")
    private Map<String, Object> payload(Device d) {
        return d.lastPayload == null ? null : json.readValue(d.lastPayload, Map.class);
    }
}
