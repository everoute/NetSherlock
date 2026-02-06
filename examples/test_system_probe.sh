#!/bin/bash

##############################################################################
# NetSherlock System Network Probe - 完整测试脚本
#
# 此脚本演示如何创建、监控和管理系统网络探测任务。
#
# 功能:
#   1. 创建多个诊断任务（延迟、丢包、连通性）
#   2. 监控任务执行进度
#   3. 获取诊断报告
#   4. 演示取消任务
#
# 用法: bash test_system_probe.sh
#
##############################################################################

set -e

# Configuration
API_URL="${API_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-test-key-12345}"
SRC_HOST="${SRC_HOST:-192.168.79.11}"
DST_HOST="${DST_HOST:-192.168.79.12}"

# Colors
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# Helper functions
log_header() {
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  $1"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
}

log_section() {
    echo -e "\n${YELLOW}$1${NC}"
}

log_info() {
    echo -e "${CYAN}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_step() {
    echo -e "${BLUE}▶ $1${NC}"
}

# Check if API is available
check_api() {
    log_step "检查 API 可用性..."
    if curl -s -H "X-API-Key: $API_KEY" "$API_URL/health" > /dev/null 2>&1; then
        log_success "API 可用"
        return 0
    else
        log_error "API 不可用"
        echo "请确保后端服务运行在: $API_URL"
        exit 1
    fi
}

# Create diagnosis task
create_diagnosis() {
    local probe_type=$1
    local description=$2
    
    log_step "创建 $probe_type 诊断任务..."
    
    local response=$(curl -s -X POST "$API_URL/diagnose" \
        -H "X-API-Key: $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{
            \"network_type\": \"system\",
            \"diagnosis_type\": \"$probe_type\",
            \"src_host\": \"$SRC_HOST\",
            \"dst_host\": \"$DST_HOST\",
            \"description\": \"$description\"
        }")
    
    if echo "$response" | jq . >/dev/null 2>&1; then
        local diagnosis_id=$(echo "$response" | jq -r '.diagnosis_id // empty')
        if [ -n "$diagnosis_id" ]; then
            log_success "任务已创建: $diagnosis_id"
            echo "$diagnosis_id"
            return 0
        fi
    fi
    
    log_error "创建失败"
    echo "$response"
    return 1
}

# Get diagnosis status
get_status() {
    local diagnosis_id=$1
    
    local response=$(curl -s -H "X-API-Key: $API_KEY" \
        "$API_URL/diagnose/$diagnosis_id")
    
    if echo "$response" | jq . >/dev/null 2>&1; then
        echo "$response"
        return 0
    else
        return 1
    fi
}

# Monitor diagnosis task
monitor_task() {
    local diagnosis_id=$1
    local max_wait=${2:-300}  # 默认 5 分钟
    local check_interval=${3:-5}
    
    log_step "监控任务进度: $diagnosis_id"
    
    local start_time=$(date +%s)
    local current_time=$start_time
    
    while [ $((current_time - start_time)) -lt $max_wait ]; do
        local response=$(get_status "$diagnosis_id")
        
        if [ $? -eq 0 ]; then
            local status=$(echo "$response" | jq -r '.status // "unknown"')
            local timestamp=$(echo "$response" | jq -r '.timestamp // "N/A"')
            
            echo -ne "\r  状态: $status | 时间: $(date '+%H:%M:%S')"
            
            case $status in
                "completed")
                    echo ""
                    log_success "任务已完成"
                    return 0
                    ;;
                "error")
                    echo ""
                    log_error "任务出错"
                    echo "$response" | jq '.error // .'
                    return 1
                    ;;
                "running"|"waiting"|"pending")
                    # 继续等待
                    ;;
                *)
                    echo ""
                    log_error "未知状态: $status"
                    return 1
                    ;;
            esac
        fi
        
        sleep $check_interval
        current_time=$(date +%s)
    done
    
    echo ""
    log_error "监控超时 (${max_wait} 秒)"
    return 1
}

# Get diagnosis report
get_report() {
    local diagnosis_id=$1
    
    log_step "获取诊断报告..."
    
    local response=$(curl -s -H "X-API-Key: $API_KEY" \
        "$API_URL/diagnose/$diagnosis_id/report")
    
    if echo "$response" | jq . >/dev/null 2>&1; then
        echo "$response" | jq '.'
        return 0
    else
        log_error "获取报告失败"
        echo "$response"
        return 1
    fi
}

# Cancel diagnosis
cancel_diagnosis() {
    local diagnosis_id=$1
    
    log_step "取消任务: $diagnosis_id"
    
    local response=$(curl -s -X POST \
        -H "X-API-Key: $API_KEY" \
        "$API_URL/diagnose/$diagnosis_id/cancel")
    
    if echo "$response" | jq . >/dev/null 2>&1; then
        local message=$(echo "$response" | jq -r '.message // .')
        log_success "取消成功: $message"
        return 0
    else
        log_error "取消失败"
        echo "$response"
        return 1
    fi
}

# List all diagnoses
list_diagnoses() {
    log_step "列出所有诊断任务..."
    
    local response=$(curl -s -H "X-API-Key: $API_KEY" \
        "$API_URL/diagnoses?limit=10")
    
    if echo "$response" | jq . >/dev/null 2>&1; then
        echo "$response" | jq '.[] | {id: .diagnosis_id, status: .status, type: .diagnosis_type, timestamp: .timestamp}' | head -20
        return 0
    else
        return 1
    fi
}

# Print task summary
print_summary() {
    local diagnosis_id=$1
    
    log_section "📊 任务摘要"
    
    local response=$(get_status "$diagnosis_id")
    if [ $? -eq 0 ]; then
        echo "$response" | jq '{
            diagnosis_id: .diagnosis_id,
            status: .status,
            timestamp: .timestamp,
            started_at: .started_at,
            completed_at: .completed_at,
            mode: .mode,
            summary: .summary
        }' | jq '.'
    fi
}

# Main test flow
main() {
    log_header "NetSherlock 系统网络探测 - 完整测试"
    
    echo ""
    log_info "API 地址: $API_URL"
    log_info "源主机: $SRC_HOST"
    log_info "目标主机: $DST_HOST"
    echo ""
    
    # 1. Check API
    check_api
    echo ""
    
    # 2. Create multiple diagnosis tasks
    log_section "1️⃣  创建诊断任务"
    
    declare -a diagnosis_ids
    
    # Latency probe
    diagnosis_ids[0]=$(create_diagnosis "latency" "测试主机间延迟")
    if [ -z "${diagnosis_ids[0]}" ]; then
        log_error "创建延迟诊断失败"
        exit 1
    fi
    echo ""
    
    # Packet drop probe
    diagnosis_ids[1]=$(create_diagnosis "packet_drop" "测试主机间丢包")
    if [ -z "${diagnosis_ids[1]}" ]; then
        log_error "创建丢包诊断失败"
        exit 1
    fi
    echo ""
    
    # Connectivity probe
    diagnosis_ids[2]=$(create_diagnosis "connectivity" "测试主机间连通性")
    if [ -z "${diagnosis_ids[2]}" ]; then
        log_error "创建连通性诊断失败"
        exit 1
    fi
    echo ""
    
    # 3. Monitor tasks
    log_section "2️⃣  监控任务进度"
    
    for i in "${!diagnosis_ids[@]}"; do
        log_info "任务 $((i+1))/3: ${diagnosis_ids[$i]}"
        monitor_task "${diagnosis_ids[$i]}" 60 5
        echo ""
    done
    
    # 4. Get reports
    log_section "3️⃣  获取诊断报告"
    
    for i in "${!diagnosis_ids[@]}"; do
        log_header "报告 $((i+1)): ${diagnosis_ids[$i]}"
        print_summary "${diagnosis_ids[$i]}"
        
        # Only show detailed report if completed
        local status=$(get_status "${diagnosis_ids[$i]}" | jq -r '.status')
        if [ "$status" == "completed" ]; then
            echo ""
            log_step "详细报告内容"
            get_report "${diagnosis_ids[$i]}"
        else
            log_info "任务未完成，跳过详细报告"
        fi
        echo ""
    done
    
    # 5. List all diagnoses
    log_section "4️⃣  列出所有任务"
    list_diagnoses
    echo ""
    
    # 6. Test cancel functionality
    log_section "5️⃣  测试取消功能"
    
    log_info "创建一个新任务进行取消测试..."
    local cancel_test_id=$(create_diagnosis "latency" "用于取消测试的任务")
    if [ -n "$cancel_test_id" ]; then
        echo ""
        sleep 2
        cancel_diagnosis "$cancel_test_id"
        echo ""
    fi
    
    # 7. Summary
    log_header "✨ 测试完成！"
    echo ""
    log_success "所有测试步骤都已成功完成"
    echo ""
    log_info "已创建的诊断任务:"
    for id in "${diagnosis_ids[@]}"; do
        echo "  • $id"
    done
    echo ""
    log_info "查询单个任务状态:"
    echo "  curl -H \"X-API-Key: $API_KEY\" \"$API_URL/diagnose/{diagnosis_id}\""
    echo ""
    log_info "查询所有任务:"
    echo "  curl -H \"X-API-Key: $API_KEY\" \"$API_URL/diagnoses\""
    echo ""
}

# Run main function
main
