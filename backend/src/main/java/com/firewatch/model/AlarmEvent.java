package com.firewatch.model;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "alarm_events")
public class AlarmEvent {
    @Id
    public String id;                   // id do ESP32 tao -> chong luu trung
    public String deviceId;
    public String kind;                 // FIRE hoac GAS
    public int gasAdc;
    public long ageMs;
    public Instant receivedAt = Instant.now();
}
