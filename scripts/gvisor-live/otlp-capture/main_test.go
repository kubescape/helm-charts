package main

import (
	"context"
	"encoding/json"
	"os"
	"strings"
	"testing"

	logs "go.opentelemetry.io/proto/otlp/collector/logs/v1"
	common "go.opentelemetry.io/proto/otlp/common/v1"
	logpb "go.opentelemetry.io/proto/otlp/logs/v1"
)

const canary = "GVS_HELM_STOP_CANARY_2026"

func str(key, value string) *common.KeyValue {
	return &common.KeyValue{Key: key, Value: &common.AnyValue{Value: &common.AnyValue_StringValue{StringValue: value}}}
}

func num(key string, value int64) *common.KeyValue {
	return &common.KeyValue{Key: key, Value: &common.AnyValue{Value: &common.AnyValue_IntValue{IntValue: value}}}
}

func export(t *testing.T, records ...*logpb.LogRecord) []map[string]any {
	t.Helper()
	file, err := os.CreateTemp(t.TempDir(), "capture")
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	request := &logs.ExportLogsServiceRequest{ResourceLogs: []*logpb.ResourceLogs{{ScopeLogs: []*logpb.ScopeLogs{{LogRecords: records}}}}}
	if _, err := (&capture{file: file, canary: []byte(canary)}).Export(context.Background(), request); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(file.Name())
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(raw), canary) {
		t.Fatal("sensitive value retained")
	}
	var rows []map[string]any
	for _, line := range strings.Split(strings.TrimSpace(string(raw)), "\n") {
		var row map[string]any
		if err := json.Unmarshal([]byte(line), &row); err != nil {
			t.Fatal(err)
		}
		rows = append(rows, row)
	}
	return rows
}

func record(body string, attributes ...*common.KeyValue) *logpb.LogRecord {
	return &logpb.LogRecord{Body: &common.AnyValue{Value: &common.AnyValue_StringValue{StringValue: body}}, Attributes: attributes}
}

func TestStopAndHealthFieldsAreKept(t *testing.T) {
	rows := export(t,
		record("RuntimeObservation", str("kind", "container_stopped"), str("termination", "signaled"), num("exit_code", 143), num("signal", 15)),
		record("RuntimeSourceHealth", str("state", "connected"), num("verified_stops", 3), num("stop_export_submitted", 3)),
		record("SomethingElse", str("args", "ignored")))
	if len(rows) != 2 {
		t.Fatalf("unexpected rows: %v", rows)
	}
	if rows[0]["exit_code"] != float64(143) || rows[0]["signal"] != float64(15) || rows[0]["termination"] != "signaled" ||
		rows[0]["unexpected_attribute_count"] != float64(0) {
		t.Fatalf("stop fields: %v", rows[0])
	}
	if rows[1]["body"] != "RuntimeSourceHealth" || rows[1]["verified_stops"] != float64(3) || rows[1]["state"] != "connected" {
		t.Fatalf("health fields: %v", rows[1])
	}
}

func TestWireCanaryIsDetectedBeforeFiltering(t *testing.T) {
	rows := export(t, record("RuntimeSourceHealth", str("args", canary), num("handshakes", 1)))
	if len(rows) != 2 || rows[0]["body"] != "CapturePrivacyFailure" || rows[1]["wire_canary_found"] != true ||
		rows[1]["unexpected_attribute_count"] != float64(1) {
		t.Fatalf("privacy failure hidden: %v", rows)
	}
}
