// A disposable experiment collector for the gVisor stop and health trial.
//
// It extends node-agent's docs/experiments/gvisor-start-integration-20261102
// collector: the whole incoming OTLP request is still checked for the privacy
// canary before anything is filtered. A request that contains it is recorded
// as a failure and rejected without writing any of its records; otherwise only
// fixed allowlists are kept. It
// now also keeps the stop fields of RuntimeObservation records and the numeric
// counters of RuntimeSourceHealth records. General node-agent logs, unknown
// attributes and attribute values outside the allowlists are never written.
//
// Build it inside a node-agent checkout, which provides the OTLP and gRPC
// modules: copy this directory under the module root and run go build there.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"flag"
	"net"
	"os"
	"os/signal"
	"sync"
	"syscall"

	logs "go.opentelemetry.io/proto/otlp/collector/logs/v1"
	common "go.opentelemetry.io/proto/otlp/common/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"
)

var observationStrings = map[string]bool{
	"source": true, "kind": true, "identity_status": true, "identity_origin": true, "node": true,
	"container.id": true, "sandbox_id": true, "runtime_handler": true, "namespace": true,
	"pod_name": true, "pod_uid": true, "container_name": true, "termination": true,
}

var observationInts = map[string]bool{"sender_reported_drops": true, "exit_code": true, "signal": true}

var healthStrings = map[string]bool{"source": true, "state": true}

// The fixed counter keys node-agent's RuntimeSourceHealth record may carry.
var healthInts = map[string]bool{
	"active_connections": true, "accepted_connections": true, "rejected_connections": true,
	"closed_connections": true, "handshakes": true, "handshake_errors": true, "received_frames": true,
	"read_errors": true, "interrupted_reads": true, "invalid_frames": true, "unresolved_starts": true,
	"ignored_frames": true, "verified_starts": true, "callbacks_completed": true,
	"sender_drop_frames": true, "queue_drops": true, "canceled_starts": true, "recheck_rejected": true,
	"export_submitted": true, "listener_failures": true, "verified_stops": true,
	"duplicate_terminals": true, "nonterminal_exits": true, "unobserved_terminations": true,
	"stop_key_missing": true, "stop_tracking_overflow": true, "stop_queue_drops": true,
	"canceled_stops": true, "stop_callbacks_completed": true, "stop_recheck_rejected": true,
	"stop_export_submitted": true,
}

type capture struct {
	logs.UnimplementedLogsServiceServer
	mu     sync.Mutex
	file   *os.File
	canary []byte
}

func keep(record map[string]any, attributes []*common.KeyValue, strings, ints map[string]bool) int {
	unexpected := 0
	for _, kv := range attributes {
		switch {
		case strings[kv.Key]:
			record[kv.Key] = kv.Value.GetStringValue()
		case ints[kv.Key]:
			record[kv.Key] = kv.Value.GetIntValue()
		default:
			unexpected++
		}
	}
	return unexpected
}

func (c *capture) Export(_ context.Context, request *logs.ExportLogsServiceRequest) (*logs.ExportLogsServiceResponse, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	wire, err := proto.Marshal(request)
	if err != nil {
		return nil, err
	}
	canaryFound := bytes.Contains(wire, c.canary)
	clear(wire)
	if canaryFound {
		// Record the failure and reject the whole request, so no attribute of
		// it, allowlisted or not, can reach the output file.
		if err := json.NewEncoder(c.file).Encode(map[string]any{"body": "CapturePrivacyFailure", "canary_received": true}); err != nil {
			return nil, err
		}
		if err := c.file.Sync(); err != nil {
			return nil, err
		}
		return nil, status.Error(codes.PermissionDenied, "privacy canary received")
	}
	for _, resource := range request.ResourceLogs {
		for _, scope := range resource.ScopeLogs {
			for _, record := range scope.LogRecords {
				body := record.Body.GetStringValue()
				var strings, ints map[string]bool
				switch body {
				case "RuntimeObservation":
					strings, ints = observationStrings, observationInts
				case "RuntimeSourceHealth":
					strings, ints = healthStrings, healthInts
				default:
					continue
				}
				output := map[string]any{"body": body, "observed_time_unix_nano": record.ObservedTimeUnixNano, "wire_canary_found": false}
				output["unexpected_attribute_count"] = keep(output, record.Attributes, strings, ints)
				if err := json.NewEncoder(c.file).Encode(output); err != nil {
					return nil, err
				}
			}
		}
	}
	if err := c.file.Sync(); err != nil {
		return nil, err
	}
	return &logs.ExportLogsServiceResponse{}, nil
}

func main() {
	listen := flag.String("listen", "127.0.0.1:4317", "bind only a trusted local experiment address")
	output := flag.String("output", "observations.jsonl", "new sanitized output file")
	canary := flag.String("canary", "GVS_HELM_STOP_CANARY_2026", "literal marker the fixture places in argv and cwd")
	flag.Parse()
	if *canary == "" {
		panic("a privacy canary is required")
	}
	file, err := os.OpenFile(*output, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		panic("cannot create experiment output")
	}
	defer file.Close()
	listener, err := net.Listen("tcp", *listen)
	if err != nil {
		panic("cannot listen for experiment logs")
	}
	server := grpc.NewServer(grpc.MaxRecvMsgSize(1 << 20))
	logs.RegisterLogsServiceServer(server, &capture{file: file, canary: []byte(*canary)})
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	go func() { <-ctx.Done(); server.Stop() }()
	if err := server.Serve(listener); err != nil && ctx.Err() == nil {
		panic("experiment log collector failed")
	}
}
