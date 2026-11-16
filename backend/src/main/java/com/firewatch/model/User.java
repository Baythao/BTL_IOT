package com.firewatch.model;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.*;

@Entity
@Table(name = "users")
public class User {
    public static final List<String> ALL_PERMISSIONS = List.of("view_status", "view_thresholds", "view_history");

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    public Long id;
    public String username;
    public String fullName;
    public String passwordHash;
    public String role = "user";        // "admin" hoac "user"
    public String permissions = "";     // vi du: "view_status,view_history"
    public boolean active = true;
    public boolean mustChange = false;  // bat doi mat khau tam
    public Instant createdAt = Instant.now();

    // Bang user_devices: danh sach thiet bi user duoc xem
    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "user_devices", joinColumns = @JoinColumn(name = "user_id"))
    @Column(name = "device_id")
    public Set<String> devices = new HashSet<>();

    public boolean isAdmin() {
        return "admin".equals(role);
    }

    public List<String> permissionList() {
        if (isAdmin()) return ALL_PERMISSIONS;
        if (permissions.isBlank()) return List.of();
        return Arrays.asList(permissions.split(","));
    }

    public boolean can(String permission) {
        return permissionList().contains(permission);
    }
}
