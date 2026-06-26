package ec2

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"strconv"
	"strings"
)

type Value map[string]any

func canonical(value any) []byte {
	data, _ := json.Marshal(value)
	return data
}

func hash(value any, length int) string {
	digest := sha256.Sum256(canonical(value))
	encoded := hex.EncodeToString(digest[:])
	if length > 0 {
		return encoded[:length]
	}
	return encoded
}

func clone(value any) any {
	data := canonical(value)
	var result any
	_ = json.Unmarshal(data, &result)
	return result
}

func cloneValue(value Value) Value {
	if value == nil {
		return Value{}
	}
	return clone(value).(map[string]any)
}

func object(value any) Value {
	if result, ok := value.(Value); ok {
		return result
	}
	if result, ok := value.(map[string]any); ok {
		return result
	}
	return Value{}
}

func objects(value any) []Value {
	list, _ := value.([]any)
	result := make([]Value, 0, len(list))
	for _, item := range list {
		result = append(result, object(item))
	}
	return result
}

func stringList(value any) []string {
	list, _ := value.([]any)
	result := make([]string, 0, len(list))
	for _, item := range list {
		result = append(result, stringValue(item))
	}
	return result
}

func stringValue(value any) string {
	if value == nil {
		return ""
	}
	if text, ok := value.(string); ok {
		return text
	}
	return fmt.Sprint(value)
}

func intValue(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	case json.Number:
		parsed, _ := typed.Int64()
		return int(parsed)
	case string:
		parsed, _ := strconv.Atoi(typed)
		return parsed
	default:
		return 0
	}
}

func boolValue(value any) bool {
	result, _ := value.(bool)
	return result
}

func valueAt(config Value, key string) any { return config[key] }

func required(value any, name string, errors *[]string) {
	if value == nil || value == "" {
		*errors = append(*errors, name+" is required")
		return
	}
	if list, ok := value.([]any); ok && len(list) == 0 {
		*errors = append(*errors, name+" is required")
	}
}

func identifier(prefix string, parts ...any) string {
	values := make([]string, 0, len(parts))
	for _, part := range parts {
		text := strings.ReplaceAll(stringValue(part), "/", "_")
		text = strings.ReplaceAll(text, ":", "_")
		values = append(values, text)
	}
	return prefix + "-" + strings.Join(values, "-")
}

func manifestPayload(artifact Value) Value {
	result := Value{}
	for _, key := range []string{"manifest_version", "ami_id", "ami_owner_account_id", "architecture", "commit_sha", "build_id", "user_data_sha256"} {
		result[key] = artifact[key]
	}
	return result
}

func releaseIdentity(config Value) Value {
	artifact := object(config["release_artifact"])
	result := manifestPayload(artifact)
	result["manifest_sha256"] = artifact["manifest_sha256"]
	return result
}

func ValidateConfig(config Value) error {
	errors := []string{}
	if stringValue(config["schema_version"]) != "ec2-module-config.v2" {
		errors = append(errors, "schema_version must be ec2-module-config.v2")
	}
	artifact := object(config["release_artifact"])
	for _, field := range []string{"manifest_version", "ami_id", "ami_owner_account_id", "architecture", "commit_sha", "build_id", "user_data_sha256", "manifest_sha256"} {
		required(artifact[field], "release_artifact."+field, &errors)
	}
	if len(errors) == 0 {
		if stringValue(artifact["manifest_sha256"]) != hash(manifestPayload(artifact), 0) {
			errors = append(errors, "release_artifact.manifest_sha256 does not match canonical manifest")
		}
		catalog := object(config["ami_catalog"])
		images := object(catalog["images"])
		image, found := images[stringValue(artifact["ami_id"])]
		if !found {
			errors = append(errors, "release_artifact.ami_id is absent from ami_catalog.images")
		} else {
			candidate := object(image)
			if candidate["owner_account_id"] != artifact["ami_owner_account_id"] {
				errors = append(errors, "release_artifact.ami_owner_account_id does not match catalog owner")
			}
			if candidate["architecture"] != artifact["architecture"] {
				errors = append(errors, "release_artifact.architecture does not match catalog architecture")
			}
			if stringValue(candidate["state"]) != "available" {
				errors = append(errors, "release_artifact.ami_id must be available")
			}
			if boolValue(candidate["deprecated"]) {
				errors = append(errors, "release_artifact.ami_id must not be deprecated")
			}
		}
	}

	asg := object(config["asg"])
	desired, minimum, maximum := intValue(asg["desired_capacity"]), intValue(asg["min_size"]), intValue(asg["max_size"])
	if desired <= 0 || desired < minimum || desired > maximum {
		errors = append(errors, "asg desired_capacity must be within min_size and max_size")
	}
	if intValue(asg["max_unavailable"]) != 1 {
		errors = append(errors, "asg.max_unavailable must be exactly 1")
	}
	if intValue(asg["pilot_size"]) != 1 {
		errors = append(errors, "asg.pilot_size must be exactly 1")
	}
	if intValue(asg["wave_size"]) < 1 {
		errors = append(errors, "asg.wave_size must be positive")
	}

	placement := object(config["placement"])
	seenIDs, seenAZs := map[string]bool{}, map[string]bool{}
	for _, subnet := range objects(placement["subnets"]) {
		id, az := stringValue(subnet["id"]), stringValue(subnet["az"])
		if stringValue(subnet["tier"]) != "private_app" { errors = append(errors, fmt.Sprintf("subnet %s must have tier private_app", id)) }
		if subnet["account_id"] != config["account_id"] { errors = append(errors, fmt.Sprintf("subnet %s must belong to configured account", id)) }
		if !strings.HasPrefix(id, "subnet-") { errors = append(errors, "subnet id must start with subnet-") }
		if !strings.HasPrefix(az, stringValue(config["region"])) { errors = append(errors, fmt.Sprintf("subnet %s has invalid availability zone", id)) }
		if seenIDs[id] { errors = append(errors, "duplicate subnet id "+id) }
		if seenAZs[az] { errors = append(errors, "duplicate availability zone "+az) }
		seenIDs[id], seenAZs[az] = true, true
	}
	minimumAZs := intValue(placement["minimum_azs"])
	if len(seenAZs) < minimumAZs { errors = append(errors, fmt.Sprintf("placement requires at least %d unique availability zones", minimumAZs)) }

	network := object(config["network"])
	alb, resolver := stringValue(network["alb_security_group_id"]), stringValue(network["resolver_security_group_id"])
	prefixLists := stringList(network["endpoint_prefix_lists"])
	if !strings.HasPrefix(alb, "sg-") { errors = append(errors, "network.alb_security_group_id must start with sg-") }
	if !strings.HasPrefix(resolver, "sg-") { errors = append(errors, "network.resolver_security_group_id must start with sg-") }
	if len(prefixLists) == 0 { errors = append(errors, "network.endpoint_prefix_lists is required") }
	seenPrefixes := map[string]bool{}
	for _, prefix := range prefixLists {
		if seenPrefixes[prefix] { errors = append(errors, "network.endpoint_prefix_lists contains duplicates") }
		seenPrefixes[prefix] = true
		if !strings.HasPrefix(prefix, "pl-") { errors = append(errors, "network.endpoint_prefix_lists entries must start with pl-") }
	}
	port := intValue(config["service_port"])
	if port < 1 || port > 65535 { errors = append(errors, "service_port must be between 1 and 65535") }
	required(object(config["rollout"])["owner_token"], "rollout.owner_token", &errors)

	seenNames := map[string]bool{}
	for _, volume := range objects(config["ebs_volumes"]) {
		name := stringValue(volume["logical_name"])
		if name == "" { errors = append(errors, "ebs_volumes.logical_name is required") } else if seenNames[name] { errors = append(errors, "duplicate ebs logical_name "+name) }
		seenNames[name] = true
		if !boolValue(volume["encrypted"]) { errors = append(errors, fmt.Sprintf("ebs volume %s is unencrypted", name)) }
		if stringValue(volume["kms_key_alias"]) == "" { errors = append(errors, fmt.Sprintf("ebs volume %s is missing kms_key_alias", name)) }
		expectedPrefix := fmt.Sprintf("arn:aws:kms:%s:%s:key/", stringValue(config["region"]), stringValue(config["account_id"]))
		if !strings.HasPrefix(stringValue(volume["kms_key_arn"]), expectedPrefix) { errors = append(errors, fmt.Sprintf("ebs volume %s kms key is outside configured account", name)) }
		if boolValue(volume["delete_on_termination"]) { errors = append(errors, fmt.Sprintf("ebs volume %s must set delete_on_termination false", name)) }
	}
	if len(errors) > 0 { return fmt.Errorf("%s", strings.Join(errors, "; ")) }
	return nil
}

func metadataOptions() Value { return Value{"http_tokens": "required", "http_endpoint": "enabled", "http_put_response_hop_limit": 1} }

func launchTemplate(config Value) Value {
	release := releaseIdentity(config)
	body := Value{"ami_id": release["ami_id"], "architecture": release["architecture"], "instance_type": config["instance_type"], "user_data_sha256": release["user_data_sha256"], "metadata_options": metadataOptions(), "provenance": Value{"commit_sha": release["commit_sha"], "build_id": release["build_id"], "manifest_sha256": release["manifest_sha256"]}}
	version := hash(body, 20)
	return Value{"id": identifier("lt", config["app"], config["environment"]), "version": version, "ami_id": body["ami_id"], "architecture": body["architecture"], "instance_type": body["instance_type"], "user_data_sha256": body["user_data_sha256"], "metadata_options": body["metadata_options"], "provenance": body["provenance"], "tags": Value{"Application": config["app"], "Environment": config["environment"], "ManagedBy": "terraform-aws-ec2-module", "ReleaseManifestSha256": release["manifest_sha256"]}}
}

func securityGroup(config Value) Value {
	network, port := object(config["network"]), intValue(config["service_port"])
	prefixes := stringList(network["endpoint_prefix_lists"]); sort.Strings(prefixes)
	return Value{"id": identifier("sg", config["app"], config["environment"]), "ingress": []any{Value{"protocol":"tcp", "from_port":port, "to_port":port, "source_security_group_id":network["alb_security_group_id"]}}, "egress": []any{Value{"protocol":"tcp", "from_port":443, "to_port":443, "prefix_list_ids":prefixes}, Value{"protocol":"udp", "from_port":53, "to_port":53, "source_security_group_id":network["resolver_security_group_id"]}, Value{"protocol":"tcp", "from_port":53, "to_port":53, "source_security_group_id":network["resolver_security_group_id"]}}}
}

func iamRole(config Value) Value {
	resources := []string{}
	for _, volume := range objects(config["ebs_volumes"]) { resources = append(resources, stringValue(volume["kms_key_arn"])) }
	sort.Strings(resources)
	return Value{"name":identifier("role", config["app"], config["environment"]), "policy":[]any{Value{"Sid":"SsmControlPlane", "Action":[]string{"ec2messages:GetMessages", "ssm:UpdateInstanceInformation", "ssmmessages:CreateControlChannel", "ssmmessages:OpenControlChannel"}, "Resource":"*", "Condition":Value{"StringEquals":Value{"aws:ResourceAccount":config["account_id"]}}}, Value{"Sid":"ReadReleaseArtifact", "Action":[]string{"s3:GetObject"}, "Resource":strings.TrimRight(stringValue(config["artifact_bucket_arn"]), "/")+"/*"}, Value{"Sid":"DecryptDataVolume", "Action":[]string{"kms:Decrypt"}, "Resource":resources}, Value{"Sid":"PublishPaymentsMetrics", "Action":[]string{"cloudwatch:PutMetricData"}, "Resource":"*", "Condition":Value{"StringEquals":Value{"cloudwatch:namespace":config["metric_namespace"]}}}}}
}

func legacyMoves() []any { return []any{Value{"from":"aws_launch_template.payments", "to":"aws_launch_template.this"}, Value{"from":"aws_autoscaling_group.payments", "to":"aws_autoscaling_group.this"}, Value{"from":"aws_security_group.payments_instance", "to":"aws_security_group.instance"}, Value{"from":"aws_iam_role.payments_instance", "to":"aws_iam_role.instance"}, Value{"from":"aws_ebs_volume.payments_data", "to":"aws_ebs_volume.data"}, Value{"from":"aws_volume_attachment.payments_data", "to":"aws_volume_attachment.data"}} }

func normalizePrior(prior Value, config Value) (Value, Value, error) {
	if len(prior) == 0 { return Value{}, Value{"legacy_state":false, "moved":[]any{}, "preserved_instance_ids":[]any{}}, nil }
	normalized := cloneValue(prior)
	legacy := stringValue(normalized["schema_version"]) != "ec2sim.aws.2"
	instances := objects(normalized["instances"])
	for _, instance := range instances {
		if _, exists := instance["slot"]; !exists {
			raw, found := object(instance["tags"])["Slot"]
			if !found { return nil, nil, fmt.Errorf("legacy instance %s is missing Slot tag", stringValue(instance["id"])) }
			parsed, err := strconv.Atoi(stringValue(raw)); if err != nil { return nil, nil, fmt.Errorf("legacy instance %s has invalid Slot tag", stringValue(instance["id"])) }
			instance["slot"] = parsed
		}
	}
	sort.Slice(instances, func(i, j int) bool { return intValue(instances[i]["slot"]) < intValue(instances[j]["slot"]) })
	normalizedInstances := make([]any, len(instances)); preserved := make([]any, len(instances)); for i, instance := range instances { normalizedInstances[i], preserved[i] = instance, instance["id"] }; normalized["instances"] = normalizedInstances
	if _, exists := normalized["release_identity"]; !exists { normalized["release_identity"] = releaseIdentity(config) }
	moved := []any{}; if legacy { moved = legacyMoves() }
	return normalized, Value{"legacy_state":legacy, "moved":moved, "preserved_instance_ids":preserved}, nil
}

func eligibleSubnets(config Value) []Value { result := objects(object(config["placement"])["subnets"]); sort.Slice(result, func(i,j int) bool { ai,aj:=stringValue(result[i]["az"]),stringValue(result[j]["az"]); if ai==aj { return stringValue(result[i]["id"])<stringValue(result[j]["id"]) }; return ai<aj }); return result }

func placementBySlot(config Value, desired int, prior []Value) map[int]Value {
	eligible := eligibleSubnets(config); ids:=map[string]bool{}; for _, subnet:=range eligible { ids[stringValue(subnet["id"])] = true }; priorBySlot:=map[int]Value{}; for _, item:=range prior { priorBySlot[intValue(item["slot"])]=item }
	result:=map[int]Value{}; for slot:=0; slot<desired; slot++ { if item,ok:=priorBySlot[slot]; ok && ids[stringValue(item["subnet_id"])] { for _,subnet:=range eligible { if subnet["id"]==item["subnet_id"] { result[slot]=subnet; break } } } else { result[slot]=eligible[slot%len(eligible)] } }; return result
}

func instance(config, template, group Value, slot int, subnet Value) Value { release:=releaseIdentity(config); return Value{"id":identifier("i",config["app"],slot,stringValue(template["version"])[:10]), "slot":slot, "subnet_id":subnet["id"], "az":subnet["az"], "public_ip_associated":false, "security_group_id":group["id"], "launch_template_version":template["version"], "ami_id":template["ami_id"], "state":"running", "health":"healthy", "tags":Value{"Application":config["app"],"Environment":config["environment"],"Slot":strconv.Itoa(slot),"CommitSha":release["commit_sha"],"BuildId":release["build_id"],"ReleaseManifestSha256":release["manifest_sha256"]}} }

func initialInstances(config, template, group Value, desired int) []Value { placements:=placementBySlot(config,desired,nil); result:=make([]Value,0,desired); for slot:=0;slot<desired;slot++ { result=append(result,instance(config,template,group,slot,placements[slot])) }; return result }

func operationID(config Value, source, target string, desired int) string { return "rollout-"+hash(Value{"app":config["app"],"environment":config["environment"],"source_manifest":source,"target_manifest":target,"desired_capacity":desired},18) }
func event(seq int, name string, desired int, slot any, wave any) Value { result:=Value{"seq":seq,"event":name,"healthy_capacity":desired,"unavailable":0}; if slot!=nil { result["slot"]=slot }; if wave!=nil { result["wave"]=wave }; return result }

func refresh(config, prior, template, group Value, desired int) ([]Value, Value, bool, error) {
	priorInstances:=objects(prior["instances"]); sort.Slice(priorInstances,func(i,j int)bool{return intValue(priorInstances[i]["slot"])<intValue(priorInstances[j]["slot"])})
	targetManifest:=stringValue(releaseIdentity(config)["manifest_sha256"]); priorRefresh:=object(object(prior["autoscaling_group"])["instance_refresh"]); inProgress:=stringValue(priorRefresh["status"])=="in_progress"
	var source, operation string; completed:=[]int{}; events:=[]Value{}
	if inProgress { if stringValue(priorRefresh["target_manifest_sha256"])!=targetManifest { return nil,nil,false,fmt.Errorf("target release changed during in-progress rollout") }; if priorRefresh["owner_token"]!=object(config["rollout"])["owner_token"] { return nil,nil,false,fmt.Errorf("stale rollout owner cannot resume in-progress operation") }; source=stringValue(priorRefresh["source_manifest_sha256"]); operation=stringValue(priorRefresh["operation_id"]); for _,value:=range objectsOrValues(priorRefresh["completed_slots"]) { completed=append(completed,intValue(value)) }; events=objects(priorRefresh["events"]) } else { source=stringValue(object(prior["release_identity"])["manifest_sha256"]); operation=operationID(config,source,targetManifest,desired) }
	placements:=placementBySlot(config,desired,priorInstances); current:=map[int]Value{}; for _,item:=range priorInstances { current[intValue(item["slot"])]=item }; target:=map[int]Value{}; for slot:=0;slot<desired;slot++ { target[slot]=instance(config,template,group,slot,placements[slot]) }
	rollout:=object(config["rollout"]); health,fault:=stringValue(rollout["candidate_health"]),stringValue(rollout["fault_point"]); if health=="" { health="passing" }; if fault=="" { fault="none" }
	makeRefresh:=func(status string,cursor int,done []int,items []Value) Value { encoded:=make([]any,len(done));for i,v:=range done{encoded[i]=v}; encodedEvents:=make([]any,len(items));for i,v:=range items{encodedEvents[i]=v}; return Value{"strategy":"pilot-then-wave","operation_id":operation,"owner_token":rollout["owner_token"],"source_manifest_sha256":source,"target_manifest_sha256":targetManifest,"status":status,"cursor":cursor,"completed_slots":encoded,"min_healthy_percentage":int(math.Ceil(float64((desired-1)*100)/float64(desired))),"max_unavailable":1,"events":encodedEvents} }
	if !inProgress && health=="fail_pilot" { events=[]Value{event(1,"pilot_launched",desired,0,nil),event(2,"pilot_unhealthy",desired,0,nil),event(3,"previous_capacity_preserved",desired,nil,nil)}; return priorInstances,makeRefresh("rolled_back",0,[]int{},events),false,nil }
	if !inProgress && health=="fail_wave" { events=[]Value{event(1,"pilot_launched",desired,0,nil),event(2,"pilot_healthy",desired,0,nil),event(3,"pilot_committed",desired,0,nil),event(4,"wave_launched",desired,nil,1),event(5,"wave_unhealthy",desired,nil,1),event(6,"previous_capacity_preserved",desired,nil,nil)}; return priorInstances,makeRefresh("rolled_back",0,[]int{},events),false,nil }
	sequence:=0; for _,item:=range events { if intValue(item["seq"])>sequence { sequence=intValue(item["seq"]) } }; hasPilot:=false;for _,slot:=range completed{if slot==0{hasPilot=true}}
	if !hasPilot { for _,name:=range []string{"pilot_launched","pilot_healthy","pilot_committed"}{sequence++;events=append(events,event(sequence,name,desired,0,nil))}; current[0]=target[0];completed=append(completed,0); if fault=="after_pilot_commit_response_lost" { mixed:=[]Value{};for slot:=0;slot<desired;slot++{if item,ok:=current[slot];ok{mixed=append(mixed,item)}};return mixed,makeRefresh("in_progress",1,completed,events),true,nil } }
	remaining:=[]int{}; completeSet:=map[int]bool{};for _,slot:=range completed{completeSet[slot]=true};for slot:=0;slot<desired;slot++{if !completeSet[slot]{remaining=append(remaining,slot)}}; waveSize:=intValue(object(config["asg"])["wave_size"]);wave:=0
	for start:=0;start<len(remaining);start+=waveSize { wave++; end:=start+waveSize;if end>len(remaining){end=len(remaining)}; slots:=remaining[start:end]; for _,name:=range []string{"wave_launched","wave_healthy","wave_committed"}{sequence++;item:=event(sequence,name,desired,nil,wave);encoded:=make([]any,len(slots));for i,slot:=range slots{encoded[i]=slot};item["slots"]=encoded;events=append(events,item)};for _,slot:=range slots{current[slot]=target[slot];completed=append(completed,slot)} }
	sequence++;events=append(events,event(sequence,"rollout_completed",desired,nil,nil));instances:=make([]Value,0,desired);for slot:=0;slot<desired;slot++{instances=append(instances,current[slot])};sort.Ints(completed);return instances,makeRefresh("completed",desired,completed,events),false,nil
}

func objectsOrValues(value any) []any { list,_:=value.([]any);return list }

func sameReleaseInstances(config, prior, template, group Value, desired int) ([]Value, []any) { priorInstances:=objects(prior["instances"]);sort.Slice(priorInstances,func(i,j int)bool{return intValue(priorInstances[i]["slot"])<intValue(priorInstances[j]["slot"]) }); placements:=placementBySlot(config,desired,priorInstances); bySlot:=map[int]Value{};for _,item:=range priorInstances{bySlot[intValue(item["slot"])]=item}; instances:=[]Value{};actions:=[]any{};for slot:=0;slot<desired;slot++{if item,ok:=bySlot[slot];ok{instances=append(instances,item);actions=append(actions,Value{"action":"no_op","slot":slot,"instance_id":item["id"]})}else{created:=instance(config,template,group,slot,placements[slot]);instances=append(instances,created);actions=append(actions,Value{"action":"create","slot":slot,"instance_id":created["id"]})}};for slot,item:=range bySlot{if slot>=desired{actions=append(actions,Value{"action":"scale_in","slot":slot,"instance_id":item["id"]})}};return instances,actions }

func driftReport(prior, expected []Value, group Value) []Value { expectedBySlot:=map[int]Value{};for _,item:=range expected{expectedBySlot[intValue(item["slot"])]=item};result:=[]Value{};for _,actual:=range prior{slot:=intValue(actual["slot"]);wanted,ok:=expectedBySlot[slot];if !ok{continue};checks:=[]struct{field string; expected any}{{"launch_template_version",wanted["launch_template_version"]},{"public_ip_associated",false},{"subnet_id",wanted["subnet_id"]},{"security_group_id",group["id"]}};for _,check:=range checks{if fmt.Sprint(actual[check.field])!=fmt.Sprint(check.expected){result=append(result,Value{"instance_id":actual["id"],"slot":slot,"field":check.field,"expected":check.expected,"actual":actual[check.field],"action":"report_only"})}}};return result }

func volumes(config Value, instances []Value, prior Value) ([]Value,error) { priorInstances:=map[string]int{};for _,item:=range objects(prior["instances"]){priorInstances[stringValue(item["id"])]=intValue(item["slot"])};priorVolumes:=map[string]Value{};for _,volume:=range objects(prior["ebs_volumes"]){slot:=intValue(volume["slot"]);attached:=stringValue(volume["attached_instance_id"]);if actual,ok:=priorInstances[attached];attached!=""&&ok&&actual!=slot{return nil,fmt.Errorf("volume %s violates slot ownership",stringValue(volume["id"]))};priorVolumes[fmt.Sprintf("%d:%s",slot,stringValue(volume["logical_name"]))]=volume};result:=[]Value{};definitions:=objects(config["ebs_volumes"]);for _,item:=range instances{slot:=intValue(item["slot"]);for _,definition:=range definitions{name:=stringValue(definition["logical_name"]);stable:=identifier("vol",config["app"],slot,name);previous:=priorVolumes[fmt.Sprintf("%d:%s",slot,name)];generation:=intValue(previous["attachment_generation"]);if len(previous)==0{generation=1}else if previous["attached_instance_id"]!=item["id"]{generation++};token:=hash(Value{"volume_id":stable,"instance_id":item["id"],"generation":generation},24);result=append(result,Value{"id":stable,"logical_name":name,"slot":slot,"size_gb":intValue(definition["size_gb"]),"encrypted":true,"kms_key_alias":definition["kms_key_alias"],"kms_key_arn":definition["kms_key_arn"],"delete_on_termination":false,"orphaned":false,"attached_instance_id":item["id"],"attachment_generation":generation,"attachment_token":token,"tags":Value{"Application":config["app"],"Environment":config["environment"],"Slot":strconv.Itoa(slot),"VolumeRole":name,"ManagedBy":"terraform-aws-ec2-module"}})}};sort.Slice(result,func(i,j int)bool{if intValue(result[i]["slot"])==intValue(result[j]["slot"]){return stringValue(result[i]["logical_name"])<stringValue(result[j]["logical_name"])};return intValue(result[i]["slot"])<intValue(result[j]["slot"])});return result,nil }

func Render(config Value, priorState Value) (Value,error) {
	if err:=ValidateConfig(config);err!=nil{return nil,err};prior,importReport,err:=normalizePrior(priorState,config);if err!=nil{return nil,err};release:=releaseIdentity(config);template,group,role:=launchTemplate(config),securityGroup(config),iamRole(config);desired:=intValue(object(config["asg"])["desired_capacity"]);priorInstances:=objects(prior["instances"]);priorRefresh:=object(object(prior["autoscaling_group"])["instance_refresh"]);inProgress:=stringValue(priorRefresh["status"])=="in_progress";releaseChanged:=len(prior)>0&&stringValue(object(prior["release_identity"])["manifest_sha256"])!=stringValue(release["manifest_sha256"])
	controlLost:=false;instances:=[]Value{};actions:=[]any{};drift:=[]Value{};refreshState:=Value{}
	if len(prior)==0 { instances=initialInstances(config,template,group,desired);done:=make([]any,desired);for i:=0;i<desired;i++{done[i]=i};refreshState=Value{"strategy":"pilot-then-wave","operation_id":nil,"owner_token":object(config["rollout"])["owner_token"],"source_manifest_sha256":nil,"target_manifest_sha256":release["manifest_sha256"],"status":"stable","cursor":desired,"completed_slots":done,"min_healthy_percentage":int(math.Ceil(float64((desired-1)*100)/float64(desired))),"max_unavailable":1,"events":[]any{}};for _,item:=range instances{actions=append(actions,Value{"action":"create","slot":item["slot"],"instance_id":item["id"]})} } else if releaseChanged||inProgress { instances,refreshState,controlLost,err=refresh(config,prior,template,group,desired);if err!=nil{return nil,err};for _,item:=range instances{actions=append(actions,Value{"action":"rolling_replace","slot":item["slot"],"instance_id":item["id"],"operation_id":refreshState["operation_id"]})} } else { expected:=initialInstances(config,template,group,desired);drift=driftReport(priorInstances,expected,group);instances,actions=sameReleaseInstances(config,prior,template,group,desired);for _,entry:=range drift{actions=append(actions,Value{"action":"report_only","instance_id":entry["instance_id"],"field":entry["field"]})};if len(priorRefresh)>0{refreshState=cloneValue(priorRefresh)}else{done:=make([]any,desired);for i:=0;i<desired;i++{done[i]=i};refreshState=Value{"strategy":"pilot-then-wave","operation_id":nil,"owner_token":object(config["rollout"])["owner_token"],"source_manifest_sha256":release["manifest_sha256"],"target_manifest_sha256":release["manifest_sha256"],"status":"stable","cursor":desired,"completed_slots":done,"min_healthy_percentage":int(math.Ceil(float64((desired-1)*100)/float64(desired))),"max_unavailable":1,"events":[]any{}}} }
	volumeList,err:=volumes(config,instances,prior);if err!=nil{return nil,err};sort.Slice(instances,func(i,j int)bool{return intValue(instances[i]["slot"])<intValue(instances[j]["slot"])});instanceIDs:=make([]any,len(instances));for i,item:=range instances{instanceIDs[i]=item["id"]};volumeIDs:=make([]any,len(volumeList));for i,item:=range volumeList{volumeIDs[i]=item["id"]};subnetIDs:=make([]any,0);for _,subnet:=range eligibleSubnets(config){subnetIDs=append(subnetIDs,subnet["id"])};driftAny:=make([]any,len(drift));for i,item:=range drift{driftAny[i]=item};instanceAny:=make([]any,len(instances));for i,item:=range instances{instanceAny[i]=item};volumeAny:=make([]any,len(volumeList));for i,item:=range volumeList{volumeAny[i]=item}
	result:=Value{"schema_version":"ec2sim.aws.2","environment":config["environment"],"application":config["app"],"release_identity":release,"launch_template":template,"security_group":group,"autoscaling_group":Value{"name":identifier("asg",config["app"],config["environment"]),"desired_capacity":desired,"min_size":intValue(object(config["asg"])["min_size"]),"max_size":intValue(object(config["asg"])["max_size"]),"subnet_ids":subnetIDs,"instance_refresh":refreshState},"instances":instanceAny,"ebs_volumes":volumeAny,"iam_role":role,"drift_report":driftAny,"import_report":importReport,"plan_actions":actions,"journal_repair":Value{"truncated_tail":false,"preserved_records":0},"control_plane_response_lost":controlLost,"outputs":Value{"launch_template_id":template["id"],"launch_template_version":template["version"],"autoscaling_group_name":identifier("asg",config["app"],config["environment"]),"instance_ids":instanceIDs,"volume_ids":volumeIDs,"rollout_operation_id":refreshState["operation_id"],"drift_report":driftAny}}
	result["state_digest"]=hash(result,0);return result,nil
}
