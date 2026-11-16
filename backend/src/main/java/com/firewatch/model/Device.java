package com.firewatch.model;

import jakarta.persistence.*;
import org.hibernate.annotations.DynamicUpdate;
import org.hibernate.annotations.ColumnTransformer;
import java.time.Instant;

/** Vong doi: PENDING -> ACTIVE <-> DISABLED -> RETIRED. Chi ACTIVE moi nhan du lieu MQTT. */
@Entity
@Table(name = "devices")
@DynamicUpdate   // chi ghi cot thay doi, tranh ghi de du lieu MQTT vua cap nhat
public class Device {
    @Id
    public String deviceId;             // trung DEVICE_ID trong firmware
    public String name;
    public String location;
    public String status = "PENDING";
    public boolean online = false;

    @Column(columnDefinition = "jsonb")
    @ColumnTransformer(write = "?::jsonb")
    public String lastPayload;          // ban tin /state moi nhat (JSON)
    public Instant lastSeen;
    public Instant createdAt = Instant.now();

    /** Kiem tra chuyen trang thai hop le. */
    public static boolean canMove(String from, String to) {
        return switch (from) {
            case "PENDING"  -> to.equals("ACTIVE") || to.equals("RETIRED");
            case "ACTIVE"   -> to.equals("DISABLED") || to.equals("RETIRED");
            case "DISABLED" -> to.equals("ACTIVE") || to.equals("RETIRED");
            default         -> false;   // RETIRED la trang thai cuoi
        };
    }
}
