import numpy as np
import cv2
import math
from ipdb import set_trace as pdb
import itertools


def remove_overlap(contours, keep):
    # sort from min to max
    contours.sort(key=lambda x: len(x), reverse=False)
    overlap_idx = []

    for i, cnt1 in enumerate(contours[:-1]):
        for j, cnt2 in enumerate(contours[i+1: ], start=i+1):
            if is_overlap(cnt1, cnt2):
                if keep == 'inner':
                    overlap_idx.append(j)
                if keep == 'outer':
                    overlap_idx.append(i)

    # # old version (keep inner)
    # for small_idx, (cnt1, cnt2) in enumerate(zip(contours[:-1], contours[1:])):
    #     if is_overlap(cnt1, cnt2):
    #         overlap_idx.append(small_idx + 1)
    
    overlap_idx = list(set(overlap_idx))
    keep_idx = [i for i in range(len(contours)) if i not in overlap_idx]
    keep_contours = [contours[idx] for idx in keep_idx]
    discard_contours = [contours[idx] for idx in overlap_idx]
    
    return keep_contours, discard_contours


def is_overlap(cnt1, cnt2):
    c1M = get_centroid(cnt1)
    c2M = get_centroid(cnt2)
    c1D = abs(cv2.pointPolygonTest(cnt1, c1M, True))
    c2D = abs(cv2.pointPolygonTest(cnt2, c2M, True))
    c1c2D = eucl_distance(c1M, c2M)

    # check contains and similar size
    if c1c2D < min(c1D, c2D) and min(c1D, c2D) / max(c1D, c2D) > (2 / 3):
        return True
    
    return False

def check_overlap(cnt_dict_list):
    label_change_list = []
    # If 2 contours are overlapped, change the label of the less group to another label.
    for i, dict_i in enumerate(cnt_dict_list[:-1]):
        for dict_j in cnt_dict_list[i+1:]:

            if is_overlap(dict_i['cnt'], dict_j['cnt']):
                if dict_i['group_weight'] > dict_j['group_weight']:
                    dict_j['group_weight'] = 0
                    label_change_list.append((dict_j['label'], dict_i['label']))
                    # print((dict_j['label'], dict_i['label']))
                else:
                    dict_i['group_weight'] = 0
                    label_change_list.append((dict_i['label'], dict_j['label']))
                    # print((dict_i['label'], dict_j['label']))
    
    # check if overlap contours are same contour , if true makes them same label
    label_group_change = []
    label_list = [x['label'] for x in cnt_dict_list]
    for (less_label, more_label) in set(label_change_list):
        # 0.5 Changeable
        overlap_times = label_change_list.count((less_label, more_label))
        less_weight = label_list.count(less_label)
        if overlap_times >= 0.5 * less_weight:
            found = False
            for label_group in label_group_change:
                if less_label in label_group:
                    found = True
                    label_group.append(more_label)
                if more_label in label_group:
                    found = True
                    label_group.insert(0, less_label)

            if not found:
                label_group_change.append([less_label, more_label])

    label_change_dic = {}
    for label_group in label_group_change:
        most_label = label_group[-1]
        for label in label_group:
            label_change_dic[label] = most_label

    checked_list = []
    for cnt_dic in cnt_dict_list:
        if cnt_dic['group_weight'] > 0:
            if cnt_dic['label'] in label_change_dic:
                cnt_dic['label'] = label_change_dic[cnt_dic['label']]
            checked_list.append(cnt_dic)

    return checked_list


def avg_img_gradient(img, model='lab'):
    '''
    Count the average gardient of the whole image, in order to compare with
    the color gradient obviousity.
    There are two uses of the 'avg_gradient'.
    1. Avoid that the image are only two color gradients, one of them will be deleted , even if they are close.
    2. If all the color gradient are less than the avg_gradient, all of them will be discarded
       since they are not obvious enough.
    '''

    kernel = np.array([[-1, -1, -1],
                       [-1, 8, -1],
                       [-1, -1, -1]])

    if model == 'lab':

        height, width = img.shape[:2]
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        lab_l = lab[:, :, 0]
        lab_a = lab[:, :, 1]
        lab_b = lab[:, :, 2]

        lab_list = [lab_l, lab_a, lab_b]
        gradient_list = []

        for lab_channel in lab_list:
            gradient = cv2.filter2D(lab_channel, -1, kernel)
            gradient_list.append(gradient)

        avg_gradient = 0.0
        for x in range(height):
            for y in range(width):
                avg_gradient += math.sqrt(
                    pow(gradient_list[0][x, y], 2) + pow(gradient_list[1][x, y], 2) + pow(gradient_list[2][x, y], 2))

        avg_gradient /= (float(height) * float(width))

    return avg_gradient

def get_centroid(cnt):
    M = cv2.moments(cnt)
    cx = int(M['m10'] / M['m00'])
    cy = int(M['m01'] / M['m00'])
    return cx, cy

def eucl_distance(a, b):
    if type(a) != np.ndarray:
        a = np.array(a)
    if type(b) != np.ndarray:
        b = np.array(b)

    return np.linalg.norm(a - b)

def evaluate_detection_performance(img, fileName, final_group_cnt, resize_ratio, evaluate_csv_path):
    '''
    Evaluation during run time.
    The evaluation is about if the contours are
    detected correctly.
    The results are compared with the groundtruth.

    @param
    evaluate_csv_path : read the groundtruth data
    '''

    tp = 0
    fp = 0
    fn = 0
    pr = 0.0
    re = 0.0
    # Mix the pr and re
    fm = 0.0
    # Only compare the count
    er = 0.0
    groundtruth_list = []
    translate_list = [['Group', 'Y', 'X']]
    with open(evaluate_csv_path + fileName + '.csv') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # groundtruth_list.append( { 'Group':int(row['Group']), 'X':int(int(row['X'])*resize_ratio), 'Y':int(int(row['Y'])*resize_ratio) } )
            groundtruth_list.append({'Group': int(row['Group']), 'X': int(row['X']), 'Y': int(row['Y'])})

    cnt_area_coordinate = Get_Cnt_Area_Coordinate(img, final_group_cnt)
    cnt_area_coordinate.sort(key=lambda x: len(x), reverse=False)

    groundtruth_count = len(groundtruth_list)
    program_count = len(cnt_area_coordinate)

    # _________The 1st Evaluation and the preprocessing of the 2nd evaluation_____________________________
    '''
    @param
    g_dic : the coordinate of one contour in the groundtruth list (g means groundtruth)
    cnt_dic : one contour(all pixels' coordinate in a contour area) in the cnt_area_coordinate
    cnt_area_coordinate : All contours that the program found in one image 

    If g_dic is in cnt_dic (which means one of the groundtruth contours matches one of the contours that the program found),
    save both label of cnt_dic and the coordinate of g_dic in the translate list.
    '''
    for g_dic in groundtruth_list:
        for cnt_dic in cnt_area_coordinate:
            if [int(g_dic['Y'] * resize_ratio), int(g_dic['X'] * resize_ratio)] in cnt_dic['coordinate']:
                tp += 1
                cnt_area_coordinate.remove(cnt_dic)
                translate_list.append([cnt_dic['label'], g_dic['Y'], g_dic['X']])
                break

    '''Make a csv that save the translate list.'''
    f = open(csv_output + fileName[:-4] + '.csv', "wb")
    w = csv.writer(f)
    w.writerows(translate_list)
    f.close()

    fp = program_count - tp
    fn = groundtruth_count - tp

    if tp + fp > 0:
        pr = tp / float(tp + fp)
    if tp + fn > 0:
        re = tp / float(tp + fn)
    if pr + re > 0:
        fm = 2 * pr * re / (pr + re)
    if groundtruth_count > 0:
        er = abs(program_count - groundtruth_count) / float(groundtruth_count)
    print(program_count, groundtruth_count)
    return tp, fp, fn, pr, re, fm, er
    # _____________________1 st evaluation end__________________________________________________

def Get_Cnt_Area_Coordinate(img, final_group_cnt):
    '''
    Take the contour list (in order) as input ,
    output all the points within the contour.
    In order to check if a point is contained in the contour.
    '''

    cnt_area_coordinate = []
    blank_img = np.zeros(img.shape[:2], np.uint8)

    for cnt_group in final_group_cnt:
        for cnt in cnt_group:
            blank_img[:] = 0
            cv2.drawContours(blank_img, [cnt], -1, 255, -1)
            # cv2.imshow('blank',blank_img)
            # cv2.waitKey(0)
            # use argwhere to find all coordinate which value == 1 ( cnt area )
            cnt_area_coordinate.append((np.argwhere(blank_img == 255)).tolist())

    return cnt_area_coordinate


# def is_overlap_by_charlie(cnt1, cnt2):
    
#     # perimeter:
#     if len(cnt1)/ len(cnt2) < 0.8:
#         return False
    
#     # area
#     c1A = cv2.contourArea(cnt1)
#     c2A = cv2.contourArea(cnt2)
#     if c1A / c2A < 0.75:
#         return False
    
#     # pdb()
#     c1M = get_centroid(cnt1)
#     c1D = abs(cv2.pointPolygonTest(cnt1, c1M, True))
#     c2M = get_centroid(cnt2)
#     c2D = abs(cv2.pointPolygonTest(cnt2, c2M, True))
#     c1c2D = eucl_distance(c1M, c2M)
#     if max(c1D, c2D) == 0:
#         pdb()
#     if c1c2D > min(c1D, c2D) or min(c1D, c2D) / max(c1D, c2D) < (2 / 3):
#         return False

#     # if intersect = not overlap
#     cnt1 = cnt1.reshape(len(cnt1), 2)
#     cnt2 = cnt2.reshape(len(cnt2), 2)
#     sets_cnt1 = set(map(lambda x: frozenset(tuple(x)), cnt1))
#     sets_cnt2 = set(map(lambda x: frozenset(tuple(x)), cnt2))
#     if len(sets_cnt1.intersection(sets_cnt2)) > 0:
#         return False

#     return True


